"""
识别路由模块 - 支持训练脚本保存的模型格式
"""

import os
import io
import base64
from functools import wraps
from PIL import Image
from flask import Blueprint, request, jsonify
import torch
import torch.nn as nn
import torch.nn.functional as F
import pymysql
from pymysql.cursors import DictCursor

from config import CHECKPOINT_PATH, MODEL_CONFIG, IMAGE_MEAN, IMAGE_STD, IMAGE_BASE_URL, DB_CONFIG


# 可选token验证（不强制要求登录）
def optional_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import g
        g.user_id = None
        g.user = None
        
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            try:
                import jwt
                from config import JWT_CONFIG
                payload = jwt.decode(token, JWT_CONFIG['secret_key'], algorithms=['HS256'])
                g.user_id = payload.get('user_id')
                # 获取用户信息
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                cursor.execute("SELECT * FROM users WHERE id = %s", (g.user_id,))
                g.user = cursor.fetchone()
                cursor.close()
                conn.close()
            except:
                pass
        return f(*args, **kwargs)
    return decorated

# 从数据库加载花卉类别名称映射
def load_classes_from_database():
    """从数据库 flower_mapping 表加载花卉类别"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(DictCursor)
        
        # 按 id 排序确保与模型输出对应
        cursor.execute("SELECT * FROM flower_mapping ORDER BY id")
        rows = cursor.fetchall()
        
        # 按 id 顺序构建列表
        classes = []
        id_to_info = {}  # id -> {folderName, latin_name, chinese_name}
        
        for row in rows:
            folder_name = row['folder_name']
            latin_name = row['latin_name']
            chinese_name = row['chinese_name']
            
            classes.append(folder_name)
            id_to_info[row['id']] = {
                'folder_name': folder_name,
                'latin_name': latin_name,
                'chinese_name': chinese_name
            }
        
        cursor.close()
        conn.close()
        
        print(f"[INFO] 从数据库加载了 {len(classes)} 个花卉类别")
        return classes, id_to_info
        
    except Exception as e:
        print(f"[ERROR] 从数据库加载类别失败: {e}")
        # 降级到文件夹方式
        return load_classes_from_folder(), None


def load_classes_from_folder():
    """从数据集目录加载花卉类别（降级方案）"""
    import os
    classes = []
    if os.path.exists(IMAGE_BASE_URL):
        for folder in sorted(os.listdir(IMAGE_BASE_URL)):
            folder_path = os.path.join(IMAGE_BASE_URL, folder)
            if os.path.isdir(folder_path):
                classes.append(folder)
    print(f"[INFO] 从数据集文件夹加载了 {len(classes)} 个花卉类别")
    return classes


# 加载类别
CLASSNAMES, _ID_TO_INFO = load_classes_from_database()
CLASSNAMES_CN = {name: name for name in CLASSNAMES}

# 如果数据库加载成功，构建 id 到信息的映射
if _ID_TO_INFO:
    _ID_TO_CLASS = _ID_TO_INFO
else:
    _ID_TO_CLASS = {}

bp = Blueprint('identify', __name__, url_prefix='/api')

# 全局模型变量
model = None
device = None
transform = None


class FlowerClassifier(nn.Module):
    """花卉分类模型 - 与train_optimized.py训练脚本保存的格式完全匹配"""
    def __init__(self, clip_model, num_classes=120):
        super().__init__()
        self.clip_model = clip_model
        feat_dim = clip_model.visual.output_dim  # 2048 for RN50
        
        # 与训练脚本 ImprovedClassifier 完全一致的分类头结构
        self.fc1 = nn.Linear(feat_dim, 512)
        self.ln1 = nn.LayerNorm(512)
        self.dropout = nn.Dropout(0.3)
        self.fc2 = nn.Linear(512, num_classes)
        
        # 初始化
        nn.init.xavier_uniform_(self.fc1.weight)
        nn.init.zeros_(self.fc1.bias)
    
    def forward(self, x):
        with torch.no_grad():
            features = self.clip_model.encode_image(x)
        x = self.fc1(features)
        x = self.ln1(x)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.fc2(x)
        return x


def load_model():
    """加载训练好的模型"""
    global model, device
    
    import torch
    import torch.nn as nn
    from torchvision import transforms
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Using device: {device}")
    
    # 1. 加载基础 CLIP 模型
    backbone_name = MODEL_CONFIG['backbone'].lstrip("CLIP-")
    print(f"[INFO] Loading base CLIP model: {backbone_name}")
    
    try:
        from config import CLIP_CACHE_DIR
        os.environ['CLIP_CACHE_DIR'] = CLIP_CACHE_DIR
        
        import clip
        clip_model, _ = clip.load(backbone_name, device=device)
        clip_model.float()
        print("[INFO] Base CLIP model loaded successfully")
        
    except Exception as e:
        print(f"[ERROR] Failed to load CLIP: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 2. 构建分类模型
    print("[INFO] Building classification model...")
    try:
        num_classes = 120
        model = FlowerClassifier(clip_model, num_classes)
        model.to(device)
        model.eval()
    except Exception as e:
        print(f"[ERROR] Failed to build model: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. 加载训练好的权重
    print(f"[INFO] Loading checkpoint from: {CHECKPOINT_PATH}")
    
    if not os.path.exists(CHECKPOINT_PATH):
        print(f"[ERROR] Checkpoint not found: {CHECKPOINT_PATH}")
        return False
    
    try:
        checkpoint = torch.load(CHECKPOINT_PATH, map_location=device, weights_only=False)
        
        # 训练脚本保存的格式: classifier_state, clip_state
        if 'classifier_state' in checkpoint:
            print("[INFO] Loading classifier weights from classifier_state...")
            classifier_state = checkpoint['classifier_state']
            model.load_state_dict(classifier_state, strict=False)
            print(f"[INFO] Classifier loaded successfully")
        
        if 'clip_state' in checkpoint:
            print("[INFO] Loading CLIP weights from clip_state...")
            clip_state = checkpoint['clip_state']
            # 移除可能的 'clip_model.' 前缀
            new_clip_state = {}
            for k, v in clip_state.items():
                new_key = k.replace('clip_model.', '')
                new_clip_state[new_key] = v
            model.clip_model.load_state_dict(new_clip_state, strict=False)
            print("[INFO] CLIP weights loaded successfully")
        
        print("[INFO] Model loaded successfully!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to load checkpoint: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_transform():
    """获取图像预处理变换"""
    global transform
    if transform is not None:
        return transform
    
    from torchvision import transforms
    
    resolution = MODEL_CONFIG['resolution']
    transform = transforms.Compose([
        transforms.Resize(resolution * 8 // 7, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop(resolution),
        transforms.ToTensor(),
        transforms.Normalize(IMAGE_MEAN, IMAGE_STD),
    ])
    return transform


@bp.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'message': 'Flower recognition service is running',
        'model_loaded': model is not None,
        'device': str(device) if device else 'not initialized'
    })


@bp.route('/classify', methods=['POST'])
@optional_token_required
def classify_flower():
    """花卉识别接口"""
    global model, device
    
    from flask import g
    import torch
    
    # 确保模型已加载
    if model is None:
        print("[INFO] Model not loaded, loading now...")
        if not load_model():
            return jsonify({
                'success': False,
                'error': 'Model failed to load'
            }), 500
    
    trans = get_transform()
    
    try:
        # 获取图片
        if request.is_json:
            data = request.get_json()
            top_k = data.get('top_k', 5)
            image_data = data.get('image', '')
            
            if not image_data:
                return jsonify({'success': False, 'error': 'Missing image data'}), 400
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        elif 'image' in request.files:
            file = request.files['image']
            top_k = int(request.form.get('top_k', 5))
            image = Image.open(file).convert('RGB')
        
        else:
            return jsonify({'success': False, 'error': 'No image provided'}), 400
        
        # 预处理图像
        img_tensor = trans(image).unsqueeze(0).to(device)
        
        # 推理
        with torch.no_grad():
            output = model(img_tensor)
            probs = torch.softmax(output, dim=1)
            top_probs, top_indices = torch.topk(probs, min(top_k, len(CLASSNAMES)), dim=1)
        
        # 构建结果
        results = []
        for prob, idx in zip(top_probs[0], top_indices[0]):
            class_id = int(idx.item())
            if class_id >= len(CLASSNAMES):
                continue
            
            english_name = CLASSNAMES[class_id]
            
            # 优先使用数据库中的信息
            if _ID_TO_CLASS and (class_id + 1) in _ID_TO_CLASS:
                info = _ID_TO_CLASS[class_id + 1]
                latin_name = info['latin_name']
                chinese_name = info['chinese_name']
            else:
                latin_name = english_name
                chinese_name = english_name
            
            results.append({
                'class_id': class_id,
                'name': english_name,
                'name_en': latin_name,
                'name_cn': chinese_name,
                'display_name': f"{chinese_name} ({latin_name})",
                'confidence': round(prob.item() * 100, 2)
            })
        
        # 如果用户已登录，添加经验值
        if g.user_id:
            try:
                from routes.user import add_experience
                add_experience(g.user_id, 'identify', '识别花卉')
            except:
                pass
        
        return jsonify({
            'success': True,
            'results': results,
            'top_result': results[0] if results else None
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/classes', methods=['GET'])
def get_classes():
    """获取所有花卉类别"""
    classes = []
    for i, name in enumerate(CLASSNAMES):
        if _ID_TO_CLASS and (i + 1) in _ID_TO_CLASS:
            info = _ID_TO_CLASS[i + 1]
            classes.append({
                'id': i,
                'name': info['folder_name'],
                'name_en': info['latin_name'],
                'name_cn': info['chinese_name']
            })
        else:
            classes.append({
                'id': i,
                'name': name,
                'name_en': name,
                'name_cn': name
            })
    
    return jsonify({
        'success': True,
        'classes': classes,
        'total': len(CLASSNAMES)
    })


# ============== 启动时尝试加载模型 ==============
print("[INFO] ========== 正在加载花卉识别模型 ==========")
try:
    load_model()
except Exception as e:
    print(f"[WARNING] 模型加载失败: {e}")
print(f"[INFO] ========== 模型加载完成 ==========")

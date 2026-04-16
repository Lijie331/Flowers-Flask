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

import os
import json

# 从 flower102_classes.json 加载类别映射
CLASS_MAPPING = {}  # index -> {en, zh}
CLASSNAMES = []  # 英文名列表
CLASSNAMES_CN = []  # 中文名列表

def load_class_mapping():
    """从 flower102_classes.json 加载模型输出到中英文的映射"""
    global CLASS_MAPPING, CLASSNAMES, CLASSNAMES_CN
    
    json_path = r"D:\1B.毕业设计\102\LIFT-main102\data\flower102_classes.json"
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # classes 是列表，每个元素是 {"id": {"en": "...", "zh": "..."}}
        for item in data.get('classes', []):
            if isinstance(item, dict):
                for cls_id, cls_info in item.items():
                    idx = int(cls_id) - 1  # id从1开始，转为0-based索引
                    CLASS_MAPPING[idx] = {
                        'id': cls_id,
                        'en': cls_info.get('en', ''),
                        'zh': cls_info.get('zh', '')
                    }
        
        # 构建英文名和中文名列表（按索引排序）
        CLASSNAMES = [CLASS_MAPPING[i]['en'] for i in sorted(CLASS_MAPPING.keys())]
        CLASSNAMES_CN = [CLASS_MAPPING[i]['zh'] for i in sorted(CLASS_MAPPING.keys())]
        
        print(f"[INFO] 从 flower102_classes.json 加载了 {len(CLASSNAMES)} 个类别映射")
        return True
    except Exception as e:
        print(f"[ERROR] 加载类别映射失败: {e}")
        return False

# 加载类别映射
load_class_mapping()

bp = Blueprint('identify', __name__, url_prefix='/api')

# 全局模型变量
model = None
device = None
transform = None


class FlowerClassifier(nn.Module):
    """花卉分类模型 - 支持LIFT训练脚本保存的CosineClassifier格式"""
    def __init__(self, clip_model, num_classes=120):
        super().__init__()
        self.clip_model = clip_model
        feat_dim = clip_model.visual.output_dim  # 2048 for RN50
        
        # LIFT使用的CosineClassifier结构
        # weight shape: (num_classes, feat_dim)
        self.weight = nn.Parameter(torch.empty(num_classes, feat_dim))
        self.scale = 30.0  # CosineClassifier的默认scale
        
        # 初始化权重
        self.weight.data.uniform_(-1, 1).renorm_(2, 0, 1e-5).mul_(1e5)
    
    def forward(self, x):
        with torch.no_grad():
            features = self.clip_model.encode_image(x)
        # CosineClassifier的forward逻辑
        x = F.normalize(features, dim=-1)
        weight = F.normalize(self.weight, dim=-1)
        return F.linear(x, weight) * self.scale


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
        # 从checkpoint中获取实际的类别数
        if os.path.exists(CHECKPOINT_PATH):
            checkpoint = torch.load(CHECKPOINT_PATH, map_location='cpu', weights_only=False)
            if 'head' in checkpoint and 'weight' in checkpoint['head']:
                num_classes = checkpoint['head']['weight'].shape[0]
                print(f"[INFO] Detected {num_classes} classes from checkpoint")
            else:
                num_classes = 120
        else:
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
        
        # LIFT训练脚本保存的格式: tuner, head
        # head 包含 CosineClassifier 的 weight 和 scale
        if 'head' in checkpoint:
            print("[INFO] Loading head weights from checkpoint...")
            head_state = checkpoint['head']
            
            # 构建新的state_dict来匹配FlowerClassifier
            new_state_dict = {}
            for k, v in head_state.items():
                if k.startswith('head.'):
                    # 移除 'head.' 前缀
                    new_key = k[5:]
                else:
                    new_key = k
                new_state_dict[new_key] = v
            
            # 加载权重
            model.load_state_dict(new_state_dict, strict=False)
            print(f"[INFO] Head weights loaded: {list(new_state_dict.keys())}")
        
        # 如果有tuner权重（可能是CLIP微调的参数）
        if 'tuner' in checkpoint:
            print("[INFO] Found tuner weights (CLIP fine-tuning)")
            # LIFT中tuner通常是空的，除非启用full_tuning
        
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
            debug_mode = data.get('debug', False)  # 添加debug参数
            
            if not image_data:
                return jsonify({'success': False, 'error': 'Missing image data'}), 400
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        elif 'image' in request.files:
            file = request.files['image']
            top_k = int(request.form.get('top_k', 5))
            image = Image.open(file).convert('RGB')
            debug_mode = request.form.get('debug', 'false').lower() == 'true'
        
        else:
            return jsonify({'success': False, 'error': 'No image provided'}), 400
        
        # 预处理图像
        img_tensor = trans(image).unsqueeze(0).to(device)
        
        # 推理
        with torch.no_grad():
            output = model(img_tensor)
            probs = torch.softmax(output, dim=1)
            top_probs, top_indices = torch.topk(probs, min(top_k, len(CLASSNAMES)), dim=1)
        
        # 如果是debug模式，返回原始模型输出
        if debug_mode:
            raw_results = []
            for prob, idx in zip(top_probs[0], top_indices[0]):
                class_id = int(idx.item())
                
                # 使用 CLASS_MAPPING 获取信息
                if class_id in CLASS_MAPPING:
                    mapping = CLASS_MAPPING[class_id]
                    chinese_name = mapping['zh']
                    english_name = mapping['en']
                else:
                    chinese_name = 'unknown'
                    english_name = f'class_{class_id}'
                
                raw_results.append({
                    'class_id': class_id,  # 0-based 索引
                    'class_id_1based': class_id + 1,  # 1-based 索引 (对应 flower102_classes.json)
                    'chinese_name': chinese_name,
                    'english_name': english_name,
                    'valid': class_id < len(CLASS_MAPPING),
                    'raw_logit': round(output[0][class_id].item(), 4),
                    'softmax_prob': round(prob.item(), 6)
                })
            
            return jsonify({
                'success': True,
                'debug': True,
                'model_output_classes': 102,
                'mapping_classes': len(CLASS_MAPPING),
                'raw_results': raw_results,
                'model_output_shape': list(output.shape)
            })
        
        # 构建结果（使用 flower102_classes.json 的映射）
        results = []
        for prob, idx in zip(top_probs[0], top_indices[0]):
            class_id = int(idx.item())
            
            # 使用 CLASS_MAPPING 获取中英文名称
            if class_id in CLASS_MAPPING:
                mapping = CLASS_MAPPING[class_id]
                english_name = mapping['en']
                chinese_name = mapping['zh']
            else:
                english_name = f"class_{class_id}"
                chinese_name = f"类别_{class_id}"
            
            results.append({
                'class_id': class_id,  # 模型输出的原始索引 (0-based)
                'class_id_1based': class_id + 1,  # 1-based 索引 (对应 flower102_classes.json)
                'name_en': english_name,
                'name_cn': chinese_name,
                'display_name': f"{chinese_name} ({english_name})",
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
    for idx in sorted(CLASS_MAPPING.keys()):
        mapping = CLASS_MAPPING[idx]
        classes.append({
            'id': idx,
            'id_1based': idx + 1,
            'name_en': mapping['en'],
            'name_cn': mapping['zh'],
            'display_name': f"{mapping['zh']} ({mapping['en']})"
        })
    
    return jsonify({
        'success': True,
        'classes': classes,
        'total': len(classes)
    })


# ============== 启动时尝试加载模型 ==============
print("[INFO] ========== 正在加载花卉识别模型 ==========")
try:
    load_model()
except Exception as e:
    print(f"[WARNING] 模型加载失败: {e}")
print(f"[INFO] ========== 模型加载完成 ==========")

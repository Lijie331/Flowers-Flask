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


# ============== 多模型配置 ==============
# 模型配置字典 - 每个模型有独立的checkpoint路径和backbone配置
MODEL_REGISTRY = {
    'clip_rn50': {
        'backbone': 'CLIP-RN50',
        'resolution': 224,
        'checkpoint': r"D:\1B.毕业设计\Flowers-Flask\output\RN50\best_model.pth.tar",
        'display_name': 'ResNet50 (快速)',
        'description': '快速识别，适合日常使用'
    },
    'clip_rn101': {
        'backbone': 'CLIP-RN101',
        'resolution': 224,
        'checkpoint': r"D:\1B.毕业设计\Flowers-Flask\output\RN101\checkpoint.pth.tar",
        'display_name': 'ResNet101 (平衡)',
        'description': '速度和精度平衡'
    },
    'clip_vit_b16': {
        'backbone': 'CLIP-ViT-B/16',
        'resolution': 224,
        'checkpoint': r"D:\1B.毕业设计\Flowers-Flask\output\ViT-B16\checkpoint.pth.tar",
        'display_name': 'ViT-B/16 (高精度)',
        'description': '高精度识别'
    },
    'clip_vit_l14': {
        'backbone': 'CLIP-ViT-L/14',
        'resolution': 224,
        'checkpoint': r"D:\1B.毕业设计\Flowers-Flask\output\ViT-L14\checkpoint.pth.tar",
        'display_name': 'ViT-L/14 (最高精度)',
        'description': '最高精度，识别效果最好'
    }
}

# 当前选中的模型名称
current_model_name = 'clip_rn50'


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
                # 从数据库验证token（与auth.py一致）
                from routes.auth import get_user_id_by_token, get_user_by_id
                user_id = get_user_id_by_token(token)
                if user_id:
                    g.user_id = user_id
                    g.user = get_user_by_id(user_id)
            except Exception as e:
                print(f"[WARN] Token验证失败: {e}")
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
    def __init__(self, clip_model, num_classes=120, weight_dim=None):
        super().__init__()
        self.clip_model = clip_model
        
        # 如果指定了weight_dim，使用它；否则从clip_model获取
        if weight_dim is not None:
            feat_dim = weight_dim
        else:
            feat_dim = clip_model.visual.output_dim
        
        print(f"[INFO] FlowerClassifier: using feature dimension = {feat_dim}")
        
        # 保存原始CLIP输出维度
        self.clip_output_dim = clip_model.visual.output_dim
        # 保存目标权重维度（从checkpoint来）
        self.target_weight_dim = feat_dim
        
        # LIFT使用的CosineClassifier结构
        # weight shape: (num_classes, feat_dim)
        self.weight = nn.Parameter(torch.empty(num_classes, feat_dim))
        self.scale = 30.0  # CosineClassifier的默认scale
        
        # 初始化权重
        self.weight.data.uniform_(-1, 1).renorm_(2, 0, 1e-5).mul_(1e5)
    
    def forward(self, x):
        # 由于已在加载时禁用了proj层，encode_image现在直接返回ln_post后的特征
        with torch.no_grad():
            features = self.clip_model.encode_image(x)
        
        # CosineClassifier的forward逻辑
        x = F.normalize(features, dim=-1)
        weight = F.normalize(self.weight, dim=-1)
        return F.linear(x, weight) * self.scale


def load_model(model_name=None):
    """加载训练好的模型"""
    global model, device, current_model_name
    
    import torch
    import torch.nn as nn
    from torchvision import transforms
    
    # 如果没有指定模型，使用当前选中的模型
    if model_name is None:
        model_name = current_model_name
    
    # 获取模型配置
    if model_name not in MODEL_REGISTRY:
        print(f"[ERROR] Unknown model: {model_name}")
        return False
    
    model_config = MODEL_REGISTRY[model_name]
    checkpoint_path = model_config['checkpoint']
    backbone_name = model_config['backbone'].lstrip("CLIP-")
    resolution = model_config['resolution']
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Loading model: {model_name} ({model_config['display_name']})")
    print(f"[INFO] Using device: {device}")
    
    # 1. 加载基础 CLIP 模型
    print(f"[INFO] Loading base CLIP model: {backbone_name}")
    
    try:
        from config import CLIP_CACHE_DIR
        os.environ['CLIP_CACHE_DIR'] = CLIP_CACHE_DIR
        
        import clip
        clip_model, _ = clip.load(backbone_name, device=device)
        clip_model.float()
        
        # 关键修复：对于ViT模型，需要跳过proj层以匹配训练时的特征维度
        # 训练时 Peft_ViT 使用 ln_post 之后的特征（投影之前）
        if 'ViT' in backbone_name and hasattr(clip_model.visual, 'proj') and clip_model.visual.proj is not None:
            print("[INFO] ViT model detected - will use features before projection layer")
            clip_model.visual.proj = None  # 禁用投影层，输出 ln_post 之后的特征
        
        print("[INFO] Base CLIP model loaded successfully")
        
    except Exception as e:
        print(f"[ERROR] Failed to load CLIP: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 2. 构建分类模型
    print("[INFO] Building classification model...")
    try:
        # 从checkpoint中获取实际的类别数和特征维度
        weight_dim = None
        if os.path.exists(checkpoint_path):
            checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
            if 'head' in checkpoint and 'weight' in checkpoint['head']:
                num_classes = checkpoint['head']['weight'].shape[0]
                weight_dim = checkpoint['head']['weight'].shape[1]  # 特征维度
                print(f"[INFO] Detected {num_classes} classes with feature dim {weight_dim} from checkpoint")
            else:
                num_classes = 102
        else:
            num_classes = 102
            print(f"[WARNING] Checkpoint not found: {checkpoint_path}, using default 102 classes")
        
        # 使用checkpoint中的weight_dim来创建分类器
        classifier_model = FlowerClassifier(clip_model, num_classes, weight_dim=weight_dim)
        classifier_model.to(device)
        classifier_model.eval()
        
    except Exception as e:
        print(f"[ERROR] Failed to build model: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. 加载训练好的权重
    print(f"[INFO] Loading checkpoint from: {checkpoint_path}")
    
    if not os.path.exists(checkpoint_path):
        print(f"[ERROR] Checkpoint not found: {checkpoint_path}")
        return False
    
    try:
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        
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
            classifier_model.load_state_dict(new_state_dict, strict=False)
            print(f"[INFO] Head weights loaded: {list(new_state_dict.keys())}")
        
        # 如果有tuner权重（可能是CLIP微调的参数）
        if 'tuner' in checkpoint:
            print("[INFO] Found tuner weights (CLIP fine-tuning)")
        
        # 更新当前模型
        model = classifier_model
        current_model_name = model_name
        print(f"[INFO] Model '{model_config['display_name']}' loaded successfully!")
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
        'model_name': current_model_name,
        'device': str(device) if device else 'not initialized'
    })


@bp.route('/models', methods=['GET'])
def get_available_models():
    """获取所有可用的模型列表"""
    models_list = []
    for name, config in MODEL_REGISTRY.items():
        checkpoint_exists = os.path.exists(config['checkpoint'])
        models_list.append({
            'value': name,
            'label': config['display_name'],
            'description': config['description'],
            'backbone': config['backbone'],
            'checkpoint_exists': checkpoint_exists,
            'is_current': name == current_model_name
        })
    
    return jsonify({
        'success': True,
        'models': models_list,
        'current_model': current_model_name
    })


@bp.route('/switch', methods=['POST'])
def switch_model():
    """切换模型接口"""
    global model, device
    
    if request.is_json:
        data = request.get_json()
        model_name = data.get('model')
    else:
        model_name = request.form.get('model')
    
    if not model_name:
        return jsonify({
            'success': False,
            'error': 'Model name is required'
        }), 400
    
    if model_name not in MODEL_REGISTRY:
        return jsonify({
            'success': False,
            'error': f'Unknown model: {model_name}'
        }), 400
    
    if model_name == current_model_name and model is not None:
        return jsonify({
            'success': True,
            'message': f'Already using model: {MODEL_REGISTRY[model_name]["display_name"]}',
            'model': model_name,
            'display_name': MODEL_REGISTRY[model_name]['display_name']
        })
    
    print(f"[INFO] Switching to model: {model_name}")
    if load_model(model_name):
        return jsonify({
            'success': True,
            'message': f'Successfully switched to: {MODEL_REGISTRY[model_name]["display_name"]}',
            'model': model_name,
            'display_name': MODEL_REGISTRY[model_name]['display_name']
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to switch model'
        }), 500


@bp.route('/classify', methods=['POST'])
@optional_token_required
def classify_flower():
    """花卉识别接口"""
    global model, device, current_model_name
    
    from flask import g
    import torch
    
    # 获取请求中的模型参数
    requested_model = None
    if request.is_json:
        data = request.get_json()
        requested_model = data.get('model')
        top_k = data.get('top_k', 5)
    elif 'image' in request.files:
        requested_model = request.form.get('model')
        top_k = int(request.form.get('top_k', 5))
    
    # 如果请求的模型与当前模型不同，需要切换模型
    if requested_model and requested_model != current_model_name:
        if requested_model in MODEL_REGISTRY:
            print(f"[INFO] Switching model from '{current_model_name}' to '{requested_model}'")
            if not load_model(requested_model):
                return jsonify({
                    'success': False,
                    'error': f'Failed to load model: {requested_model}'
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': f'Unknown model: {requested_model}'
            }), 400
    
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
        # 获取图片和原始数据
        image_data = ''  # 用于保存历史记录
        if request.is_json:
            data = request.get_json()
            top_k = data.get('top_k', 5)
            image_data = data.get('image', '')
            debug_mode = data.get('debug', False)
            
            if not image_data:
                return jsonify({'success': False, 'error': 'Missing image data'}), 400
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        elif 'image' in request.files:
            file = request.files['image']
            top_k = int(request.form.get('top_k', 5))
            image = Image.open(file).convert('RGB')
            debug_mode = request.form.get('debug', 'false').lower() == 'true'
            # 对于文件上传，暂时不支持保存图片
            image_data = ''
        
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
        print(f"[DEBUG] g.user_id = {g.user_id}")
        # 保存识别历史记录（仅保存已登录用户的记录）
        if g.user_id and results and len(results) > 0:
            try:
                top_result = results[0]
                
                # 准备top_results JSON数据
                top_results_json = json.dumps(results[:5], ensure_ascii=False)
                
                # 保存到数据库（置信度存为0-1的小数，图片存为base64）
                print(f"[DEBUG] 开始保存历史记录...")
                print(f"[DEBUG] user_id: {g.user_id}")
                print(f"[DEBUG] image_data长度: {len(image_data) if image_data else 0}")
                
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor()
                sql = """
                INSERT INTO identify_history 
                (user_id, image_url, model_name, predicted_class_id, predicted_class_name, 
                 predicted_class_en, confidence, top_results)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    g.user_id,  # 用户ID
                    image_data[:30000] if len(image_data) > 30000 else image_data,  # 图片base64（限制30KB）
                    current_model_name,  # 模型名称
                    top_result['class_id'],  # 预测类别ID
                    top_result['name_cn'],  # 中文名
                    top_result['name_en'],  # 英文名
                    top_result['confidence'] / 100.0,  # 置信度转为0-1
                    top_results_json  # JSON格式的top结果
                ))
                conn.commit()
                cursor.close()
                conn.close()
                print(f"[INFO] 识别历史已保存: {top_result['name_cn']} ({top_result['confidence']}%)")
            except Exception as e:
                import traceback
                print(f"[ERROR] 保存识别历史失败: {e}")
                print(f"[ERROR] 详细错误: {traceback.format_exc()}")
        
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


@bp.route('/identify/history', methods=['GET'])
@optional_token_required
def get_identify_history():
    """获取用户的识别历史记录（最近20条）"""
    from flask import g
    
    user_id = g.user_id
    
    # 如果未登录，返回空列表
    if not user_id:
        return jsonify({
            'success': True,
            'history': [],
            'total': 0,
            'message': '未登录用户无历史记录'
        })
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        sql = """
        SELECT id, model_name, predicted_class_id, predicted_class_name, 
               predicted_class_en, confidence, top_results, image_url, created_at
        FROM identify_history
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 20
        """
        cursor.execute(sql, (user_id,))
        records = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # 转换置信度为百分比格式
        history = []
        for record in records:
            top_results = record['top_results']
            if isinstance(top_results, str):
                top_results = json.loads(top_results)
            
            history.append({
                'id': record['id'],
                'model_name': record['model_name'],
                'model_display': MODEL_REGISTRY.get(record['model_name'], {}).get('display_name', record['model_name']),
                'predicted_class_id': record['predicted_class_id'],
                'predicted_class_name': record['predicted_class_name'],
                'predicted_class_en': record['predicted_class_en'],
                'confidence': round(record['confidence'] * 100, 2),  # 转为百分比
                'top_results': top_results,
                'image_url': record['image_url'] if record['image_url'] else None,  # 图片base64
                'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S') if record['created_at'] else None
            })
        
        return jsonify({
            'success': True,
            'history': history,
            'total': len(history)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============== 启动时尝试加载模型 ==============
print("[INFO] ========== 正在加载花卉识别模型 ==========")
try:
    load_model(current_model_name)
except Exception as e:
    print(f"[WARNING] 模型加载失败: {e}")
print(f"[INFO] ========== 模型加载完成 ==========")

"""
配置文件 - 集中管理所有配置项
"""

import os

# ============== 项目路径配置 ==============
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = r'D:\1B.毕业设计\数据集'
FLOWER_CLASSES_FILE = os.path.join(DATA_ROOT, 'flowers_data_120.json')

CLIP_CACHE_DIR = r'D:\1B.毕业设计\CLIP_cache'

# 图片数据集路径（所有花卉图片已合并到此目录）
IMAGE_BASE_URL = os.path.join(DATA_ROOT, 'ChineseFlowers120')

# 模型路径
CHECKPOINT_PATH = os.path.join(
    PROJECT_ROOT, 
    'output', 
    'best_model.pth.tar',  # 使用LIFT训练输出的模型文件
)

# ============== 数据库配置 ==============
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '314331',
    'database': 'tlj',
    'charset': 'utf8mb4'
}

# ============== 模型配置 ==============
MODEL_CONFIG = {
    'backbone': 'CLIP-RN50',
    # 'backbone': 'ViT-B/32',
    'resolution': 224,
    'prompt': 'default',
    'scale': 1.0,
    'learnable_scale': False,
    'bias': 'none',
    'init_style': 'uniform',
    'full_tuning': False,
    'classifier': 'CosineClassifier',
    'bias_tuning': False,
    'bn_tuning': False,
    'ln_tuning': False,
    'vpt_shallow': False,
    'vpt_deep': False,
    'adapter': False,
    'adaptformer': False,
    'lora': False,
    'lora_mlp': False,
    'ssf_attn': False,
    'ssf_mlp': False,
    'ssf_ln': False,
    'mask': False,
    'partial': None,
    'vpt_len': None,
    'adapter_dim': 64,
    'mask_ratio': 0.0,
    'mask_seed': 42,
}

# 图片预处理参数
IMAGE_MEAN = [0.48145466, 0.4578275, 0.40821073]
IMAGE_STD = [0.26862954, 0.26130258, 0.27577711]

# ============== Flask配置 ==============
FLASK_CONFIG = {
    'host': '127.0.0.1',
    'port': 5000,
    'debug': True,
}

# ============== JWT配置 ==============
JWT_CONFIG = {
    'secret_key': 'your-secret-key-change-in-production',
    'token_expire_hours': 24,
}

# ============== 环境变量设置 ==============
def init_env():
    """初始化环境变量"""
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    os.environ['CLIP_CACHE_DIR'] = CLIP_CACHE_DIR

# 启动时自动初始化
init_env()

# ============== 阿里云内容审核配置 ==============
ALIYUN_CONTENT_MODERATION = {
    'access_key_id': 'LTAI5t9XhhSYYWHVHsHjV7RT',
    'access_key_secret': 'i5jYF5DNlofWtPzkBB00YAmCcIqHsM',
    'region': 'cn-shanghai',
    'endpoint': 'green.cn-shanghai.aliyuncs.com',
    'scenes': ['text', 'image', 'video'],
    'thresholds': {
        'P0': 60,
        'P1': 50,
        'P2': 30,
    },
    'P0_LABELS': ['politics', 'terror', 'minor', 'propaganda', 'extremism', 'cult'],
    'P1_LABELS': ['porn', 'vulgar', 'gore', 'violence', 'advertising', 'junk'],
    'P2_LABELS': ['minor_abuse', 'soft_ad'],
}

# 是否启用AI内容审核
ENABLE_CONTENT_MODERATION = True

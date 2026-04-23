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
    'access_key_id': os.environ.get('OSS_ACCESS_KEY_ID'),
    'access_key_secret': os.environ.get('OSS_ACCESS_KEY_SECRET'),
    'region': 'cn-shanghai',
    'endpoint': 'green-cip.cn-shanghai.aliyuncs.com',
    'app_id': 'img_txt_check_agent_01',
    'scenes': ['text', 'image', 'video'],
    'thresholds': {
        'P0': 60,
        'P1': 50,
        'P2': 30,
    },
    'P0_LABELS': [
        # 英文标签（文本审核）
        'politics', 'terror', 'extremism', 'cult', 'illegal_content',
        'inappropriate_profanity', 'political_figure', '诱导犯罪',
        # 中文标签（图片审核）
        '涉政敏感', '暴恐血腥', '邪教_封建迷信违规', '教唆违法_危害公共安全',
        '侮辱英烈_历史虚无主义', '未成年人保护相关违规'
    ],
    'P1_LABELS': [
        # 英文标签（文本审核）
        'porn', 'vulgar', 'violence', 'advertising', 'junk', 'fraud',
        'hate_speech', 'personal_attack', 'security_ threat', '钓鱼',
        'inappropriate',
        # 中文标签（图片审核）
        '色情低俗', '辱骂谩骂人身攻击', '垃圾广告_营销导流', '违禁物品_违法交易',
        '诈骗_赌博_洗钱诱导', '仇恨言论_歧视', '隐私信息泄露', '恶意网址_木马引流'
    ],
    'P2_LABELS': ['minor_abuse', 'soft_ad', '诱导未成年人'],
    # 标签中文映射（用于前端显示）
    'LABEL_DISPLAY_MAP': {
        # 英文转中文
        'politics': '涉政敏感',
        'terror': '暴恐血腥',
        'extremism': '极端主义',
        'cult': '邪教封建迷信',
        'illegal_content': '违法内容',
        'inappropriate_profanity': '不当脏话',
        'political_figure': '政治敏感人物',
        '诱导犯罪': '诱导犯罪',
        'porn': '色情低俗',
        'vulgar': '低俗内容',
        'violence': '暴力内容',
        'advertising': '广告推广',
        'junk': '垃圾广告',
        'fraud': '欺诈诈骗',
        'hate_speech': '仇恨言论',
        'personal_attack': '人身攻击',
        'inappropriate': '调性异常',
        'security_threat': '安全威胁',
        '钓鱼': '钓鱼诈骗',
        'minor_abuse': '未成年人违规',
        'soft_ad': '软色情',
        '诱导未成年人': '诱导未成年人',
        # 中文标签（直接显示）
        '涉政敏感': '涉政敏感',
        '暴恐血腥': '暴恐血腥',
        '色情低俗': '色情低俗',
        '辱骂谩骂人身攻击': '辱骂谩骂人身攻击',
        '垃圾广告_营销导流': '垃圾广告营销导流',
        '违禁物品_违法交易': '违禁物品违法交易',
        '诈骗_赌博_洗钱诱导': '诈骗赌博洗钱诱导',
        '仇恨言论_歧视': '仇恨言论歧视',
        '教唆违法_危害公共安全': '教唆违法危害公共安全',
        '隐私信息泄露': '隐私信息泄露',
        '恶意网址_木马引流': '恶意网址木马引流',
        '邪教_封建迷信违规': '邪教封建迷信违规',
        '未成年人保护相关违规': '未成年人保护相关违规',
        '侮辱英烈_历史虚无主义': '侮辱英烈历史虚无主义',
    },
}

# ============== 阿里云OSS配置 ==============
ALIYUN_OSS = {
    'access_key_id': os.environ.get('OSS_ACCESS_KEY_ID'),
    'access_key_secret': os.environ.get('OSS_ACCESS_KEY_SECRET'),
    'endpoint': 'oss-cn-beijing.aliyuncs.com',
    'bucket_name': 'flowers-buck',
}

# 是否启用AI内容审核
ENABLE_CONTENT_MODERATION = True

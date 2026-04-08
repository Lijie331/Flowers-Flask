"""
utils包初始化文件
"""
import random
import numpy as np
import torch

from .security import (
    hash_password,
    verify_password,
    generate_token,
    verify_token,
    get_user_from_token,
    token_required,
    success_response,
    error_response,
    paginate,
)
from .logger import Logger, setup_logger
from .meter import AverageMeter


def accuracy(output, target, topk=(1,)):
    """计算top-k准确率"""
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)
        
        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))
        
        res = []
        for k in topk:
            correct_k = correct[:k].reshape(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res


def set_seed(seed=0):
    """设置随机种子"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


__all__ = [
    'hash_password',
    'verify_password',
    'generate_token',
    'verify_token',
    'get_user_from_token',
    'token_required',
    'success_response',
    'error_response',
    'paginate',
    'Logger',
    'setup_logger',
    'AverageMeter',
    'accuracy',
    'set_seed',
]

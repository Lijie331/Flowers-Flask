import torch

class AverageMeter:
    """Compute and store the average and current value."""

    def __init__(self, ema=False):
        self.ema = ema
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        if isinstance(val, torch.Tensor):
            val = val.item()

        self.val = val
        self.sum += val * n
        self.count += n

        if self.ema:
            self.avg = val if self.count == n else self.avg * 0.9 + self.val * 0.1
        else:
            self.avg = self.sum / self.count

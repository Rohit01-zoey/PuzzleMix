import torch
import torch.nn as nn
import torch.nn.functional as F

from torch.autograd import Variable
import sys, os
import numpy as np
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from mixup import to_one_hot, mixup_process, get_lambda, collate_mix_batch
import random


class PreActBlock(nn.Module):
    '''Pre-activation version of the BasicBlock.'''
    expansion = 1

    def __init__(self, in_planes, planes, stride=1):
        super(PreActBlock, self).__init__()
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.conv1 = nn.Conv2d(in_planes,
                               planes,
                               kernel_size=3,
                               stride=stride,
                               padding=1,
                               bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=1, padding=1, bias=False)

        if stride != 1 or in_planes != self.expansion * planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes,
                          self.expansion * planes,
                          kernel_size=1,
                          stride=stride,
                          bias=False))

    def forward(self, x):
        out = F.relu(self.bn1(x))
        shortcut = self.shortcut(out) if hasattr(self, 'shortcut') else x
        out = self.conv1(out)
        out = self.conv2(F.relu(self.bn2(out)))
        out += shortcut
        return out


class PreActBottleneck(nn.Module):
    '''Pre-activation version of the original Bottleneck module.'''
    expansion = 4

    def __init__(self, in_planes, planes, stride=1):
        super(PreActBottleneck, self).__init__()
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.conv1 = nn.Conv2d(in_planes, planes, kernel_size=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, self.expansion * planes, kernel_size=1, bias=False)

        if stride != 1 or in_planes != self.expansion * planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes,
                          self.expansion * planes,
                          kernel_size=1,
                          stride=stride,
                          bias=False))

    def forward(self, x):
        out = F.relu(self.bn1(x))
        shortcut = self.shortcut(out) if hasattr(self, 'shortcut') else x
        out = self.conv1(out)
        out = self.conv2(F.relu(self.bn2(out)))
        out = self.conv3(F.relu(self.bn3(out)))
        out += shortcut
        return out


class PreActResNet(nn.Module):
    def __init__(self, block, num_blocks, initial_channels, num_classes, stride=1):
        super(PreActResNet, self).__init__()
        self.in_planes = initial_channels
        self.num_classes = num_classes
        self.conv1 = nn.Conv2d(3,
                               initial_channels,
                               kernel_size=3,
                               stride=stride,
                               padding=1,
                               bias=False)
        self.layer1 = self._make_layer(block, initial_channels, num_blocks[0], stride=1)
        self.layer2 = self._make_layer(block, initial_channels * 2, num_blocks[1], stride=2)
        self.layer3 = self._make_layer(block, initial_channels * 4, num_blocks[2], stride=2)
        self.layer4 = self._make_layer(block, initial_channels * 8, num_blocks[3], stride=2)
        self.linear = nn.Linear(initial_channels * 8 * block.expansion, num_classes)

    def _make_layer(self, block, planes, num_blocks, stride):
        strides = [stride] + [1] * (num_blocks - 1)
        layers = []
        for stride in strides:
            layers.append(block(self.in_planes, planes, stride))
            self.in_planes = planes * block.expansion
        return nn.Sequential(*layers)

    def compute_h1(self, x):
        out = x
        out = self.conv1(out)
        out = self.layer1(out)
        return out

    def compute_h2(self, x):
        out = x
        out = self.conv1(out)
        out = self.layer1(out)
        out = self.layer2(out)
        return out

    def forward(self,
                x,
                target=None,
                mixup=False,
                mixup_hidden=False,
                args=None,
                grad=None,
                noise=None,
                adv_mask1=0,
                adv_mask2=0,
                mp=None,
                PMU=0,
                model_t = None):

        if mixup_hidden:
            layer_mix = random.randint(0, 2)
        elif mixup:
            layer_mix = 0
        else:
            layer_mix = None

        out = x

        if target is not None:
            if layer_mix is not None:
                target_reweighted_ohe = to_one_hot(target, self.num_classes)
            else:
                target_reweighted = to_one_hot(target, self.num_classes)

        if layer_mix == 0:
            out, target_reweighted = mixup_process(out,
                                                   target_reweighted_ohe,
                                                   args=args,
                                                   grad=grad,
                                                   noise=noise,
                                                   adv_mask1=adv_mask1,
                                                   adv_mask2=adv_mask2,
                                                   mp=mp)
            
            if args.unixkd:
                PMU = int(PMU) # convert it to integer for slicing
                out, target_reweighted = out[:PMU], target_reweighted[:PMU]
            else:
                out, target_reweighted = collate_mix_batch((x, target_reweighted_ohe), (out, target_reweighted), PMU=PMU)

        if model_t is not None:
            with torch.no_grad():
                out_t = model_t(out)

        out = self.conv1(out)
        out = self.layer1(out)

        if layer_mix == 1:
            out, target_reweighted = mixup_process(out, target_reweighted, args=args, hidden=True)

        out = self.layer2(out)
        if layer_mix == 2:
            out, target_reweighted = mixup_process(out, target_reweighted, args=args, hidden=True)

        out = self.layer3(out)
        if layer_mix == 3:
            out, target_reweighted = mixup_process(out, target_reweighted, args=args, hidden=True)
        out = self.layer4(out)
        out = F.avg_pool2d(out, 4)
        out = out.reshape(out.size(0), -1)
        out = self.linear(out)

        # if target is not None:
        #     return out, target_reweighted
        # else:
        #     return out

        if target is not None:
            if model_t is not None:
                return out, target_reweighted, out_t
            else:
                return out, target_reweighted
        
        else:
            if model_t is not None:
                return out, out_t
            else:
                return out


def preactresnet18(num_classes=10, dropout=False, stride=1):
    return PreActResNet(PreActBlock, [2, 2, 2, 2], 64, num_classes, stride=stride)


def preactresnet34(num_classes=10, dropout=False, stride=1):
    return PreActResNet(PreActBlock, [3, 4, 6, 3], 64, num_classes, stride=stride)


def preactresnet50(num_classes=10, dropout=False, stride=1):
    return PreActResNet(PreActBottleneck, [3, 4, 6, 3], 64, num_classes, stride=stride)


def preactresnet101(num_classes=10, dropout=False, stride=1):
    return PreActResNet(PreActBottleneck, [3, 4, 23, 3], 64, num_classes, stride=stride)


def preactresnet152(num_classes=10, dropout=False, stride=1):
    return PreActResNet(PreActBottleneck, [3, 8, 36, 3], 64, num_classes, stride=stride)


def test():
    net = preactresnet34()
    y = net(Variable(torch.randn(1, 3, 32, 32)))
    print(y.size())


if __name__ == "__main__":
    test()
# test()

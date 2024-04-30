"""The models subpackage contains definitions for the following model
architectures:
-  `ResNeXt` for CIFAR10 CIFAR100
You can construct a model with random weights by calling its constructor:
.. code:: python
    import models
    net = models.preactresnet18(num_classes)
..
"""

from .preresnet import preactresnet18, preactresnet34, preactresnet50, preactresnet101, preactresnet152
from .wide_resnet import wrn28_10, wrn28_2
from .resnetV1 import resnet20, resnet32, resnet44, resnet56, resnet110, resnet8x4, resnet14x4, resnet32x4


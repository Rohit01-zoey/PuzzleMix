# Changes made to puzzlemix

- intial parameters changed to allow for PMU, KD etc and associated parameters
- resnet models are updated with mixup (similar to preactresnet models included in the original code)
- these include PMU (partial MixUP) as well as teacher logits for KD
- KD loss is added in addition to the existing BCE loss in the original code
- `z_optmizer.py` files includes the code for the some intial attempts at using the SLSQP optimizer for the z-optmization (new code at [])
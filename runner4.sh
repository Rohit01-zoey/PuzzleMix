# CUDA_VISIBLE_DEVICES=2 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch preactresnet18  --learning_rate 0.2 --momentum 0.9 --decay 0.0001 --epochs 300 --schedule 100 200 --gammas 0.1 0.1 --train mixup --mixup_alpha 1.0 --seed 0

# CUDA_VISIBLE_DEVICES=2 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch preactresnet18  --learning_rate 0.2 --momentum 0.9 --decay 0.0001 --epochs 300 --schedule 100 200 --gammas 0.1 0.1 --train mixup_hidden --mixup_alpha 2.0 --seed 0

# CUDA_VISIBLE_DEVICES=2 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch preactresnet18  --learning_rate 0.2 --momentum 0.9 --decay 0.0001 --epochs 300 --schedule 100 200 --gammas 0.1 0.1 --train mixup --mixup_alpha 1.0 --box True --seed 0


# CUDA_VISIBLE_DEVICES=5 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100  --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train vanilla --seed 46 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1

# CUDA_VISIBLE_DEVICES=6 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --box True --seed 0 --pmu 1 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1

# CUDA_VISIBLE_DEVICES=3 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --box True --seed 23 --pmu 1 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1

# CUDA_VISIBLE_DEVICES=5 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --box True --seed 46 --pmu 1 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1

seeds=(0 23 46)

for seed in "${seeds[@]}"; do
    counter=0
    while [ $counter -lt 3 ]; do
        CUDA_VISIBLE_DEVICES=1 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./clean_experiments_RN32x4[T]_PARN18[S]/cifar100  --labels_per_class 500 --arch preactresnet18  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --graph True --n_labels 3 --eta 0.2 --beta 1.2 --gamma 0.5 --neigh_size 4 --transport True --t_size 4 --t_eps 0.8 --seed $seed --pmu 1.0 --kd True --model_t resnet32x4 --bce_weight 0 --kl_weight 1 && break
        counter=$((counter+1))
        echo "Attempt $counter for seed $seed failed. Retrying..."
        sleep 1
    done

    if [ $counter -eq 3 ]; then
        echo "Command for seed $seed failed after 3 attempts."
    fi
done
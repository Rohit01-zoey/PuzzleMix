

counter=0
while [ $counter -lt 3 ]; do
    CUDA_VISIBLE_DEVICES=3 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --graph True --n_labels 3 --eta 0.2 --beta 1.2 --gamma 0.5 --neigh_size 4 --transport True --t_size 4 --t_eps 0.8 --seed 0 --pmu 1 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1 && break
    counter=$((counter+1))
    echo "Attempt $counter failed. Retrying..."
    sleep 1
done

if [ $counter -eq 3 ]; then
    echo "Command failed after 3 attempts."
fi



# CUDA_VISIBLE_DEVICES=4 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --graph True --n_labels 3 --eta 0.2 --beta 1.2 --gamma 0.5 --neigh_size 4 --transport True --t_size 4 --t_eps 0.8 --seed 23 --pmu 1 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1
counter=0
while [ $counter -lt 3 ]; do
    CUDA_VISIBLE_DEVICES=3 python main.py --dataset cifar100 --data_dir ./data/cifar100/ --root_dir ./experiments/cifar100 --labels_per_class 500 --arch resnet20  --learning_rate 0.05 --momentum 0.9 --decay 0.0001 --epochs 240 --schedule 150 180 210 --gammas 0.1 0.1 0.1 --train mixup --mixup_alpha 1.0 --graph True --n_labels 3 --eta 0.2 --beta 1.2 --gamma 0.5 --neigh_size 4 --transport True --t_size 4 --t_eps 0.8 --seed 46 --pmu 1 --kd True --model_t resnet56 --bce_weight 0 --kl_weight 1 && break
    counter=$((counter+1))
    echo "Attempt $counter failed. Retrying..."
    sleep 1
done

if [ $counter -eq 3 ]; then
    echo "Command failed after 3 attempts."
fi
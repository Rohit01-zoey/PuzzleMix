from __future__ import division
# Codes are borrowed from https://github.com/vikasverma1077/manifold_mixup/tree/master/supervised

import os, sys, shutil, time, random
from collections import OrderedDict

sys.path.append('..')
if sys.version_info[0] < 3:
    import cPickle as pickle
else:
    import _pickle as pickle
import argparse
import numpy as np
import torch
import torch.backends.cudnn as cudnn
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from load_data import load_data_subset
from logger import plotting, copy_script_to_folder, AverageMeter, RecorderMeter, time_string, convert_secs2time
import models
from multiprocessing import Pool

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from mixup import to_one_hot, mixup_process, get_lambda, collate_mix_batch
from z_optimizer import z_optimizer

model_names = sorted(
    name for name in models.__dict__
    if name.islower() and not name.startswith("__") and callable(models.__dict__[name]))


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


parser = argparse.ArgumentParser(description='Train Classifier with mixup',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
# Data
parser.add_argument('--dataset',
                    type=str,
                    default='cifar10',
                    choices=['cifar10', 'cifar100', 'tiny-imagenet-200'],
                    help='Choose between Cifar10/100 and Tiny-ImageNet.')
parser.add_argument('--data_dir',
                    type=str,
                    default='cifar10',
                    help='file where results are to be written')
parser.add_argument('--root_dir',
                    type=str,
                    default='experiments',
                    help='folder where results are to be stored')
parser.add_argument('--labels_per_class',
                    type=int,
                    default=5000,
                    metavar='NL',
                    help='labels_per_class')
parser.add_argument('--valid_labels_per_class',
                    type=int,
                    default=0,
                    metavar='NL',
                    help='validation labels_per_class')

# Model
parser.add_argument('--arch',
                    metavar='ARCH',
                    default='wrn28_10',
                    choices=model_names,
                    help='model architecture: ' + ' | '.join(model_names) + ' (default: wrn28_10)')
parser.add_argument('--initial_channels', type=int, default=64, choices=(16, 64))

# Optimization options
parser.add_argument('--epochs', type=int, default=300, help='number of epochs to train')
parser.add_argument('--train',
                    type=str,
                    default='vanilla',
                    choices=['vanilla', 'mixup', 'mixup_hidden', 'optim_mix'],
                    help='mixup layer')
parser.add_argument('--in_batch',
                    type=str2bool,
                    default=False,
                    help='whether to use different lambdas in batch')
parser.add_argument('--mixup_alpha', type=float, help='alpha parameter for mixup')
parser.add_argument('--dropout',
                    type=str2bool,
                    default=False,
                    help='whether to use dropout or not in final layer')

# Puzzle Mix
parser.add_argument('--box', type=str2bool, default=False, help='true for CutMix')
parser.add_argument('--graph', type=str2bool, default=False, help='true for PuzzleMix')
parser.add_argument('--neigh_size',
                    type=int,
                    default=4,
                    help='neighbor size for computing distance beteeen image regions')
parser.add_argument('--n_labels', type=int, default=3, help='label space size')

parser.add_argument('--beta', type=float, default=1.2, help='label smoothness')
parser.add_argument('--gamma', type=float, default=0.5, help='data local smoothness')
parser.add_argument('--eta', type=float, default=0.2, help='prior term')

parser.add_argument('--transport', type=str2bool, default=True, help='whether to use transport')
parser.add_argument('--t_eps', type=float, default=0.8, help='transport cost coefficient')
parser.add_argument('--t_size',
                    type=int,
                    default=-1,
                    help='transport resolution. -1 for using the same resolution with graphcut')

parser.add_argument('--adv_eps', type=float, default=10.0, help='adversarial training ball')
parser.add_argument('--adv_p', type=float, default=0.0, help='adversarial training probability')

parser.add_argument('--clean_lam', type=float, default=0.0, help='clean input regularization')
parser.add_argument('--mp', type=int, default=8, help='multi-process for graphcut (CPU)')

# training
parser.add_argument('--batch_size', type=int, default=64) #! earlier was set to 100!
parser.add_argument('--learning_rate', type=float, default=0.1)
parser.add_argument('--momentum', type=float, default=0.9)
parser.add_argument('--decay', type=float, default=0.0001, help='weight decay (L2 penalty)')
parser.add_argument('--schedule',
                    type=int,
                    nargs='+',
                    default=[150, 225],
                    help='decrease learning rate at these epochs')
parser.add_argument(
    '--gammas',
    type=float,
    nargs='+',
    default=[0.1, 0.1],
    help='LR is multiplied by gamma on schedule, number of gammas should be equal to schedule')

# Checkpoints
parser.add_argument('--print_freq',
                    default=100,
                    type=int,
                    metavar='N',
                    help='print frequency (default: 200)')
parser.add_argument('--resume',
                    default='',
                    type=str,
                    metavar='PATH',
                    help='path to latest checkpoint (default: none)')
parser.add_argument('--start_epoch',
                    default=0,
                    type=int,
                    metavar='N',
                    help='manual epoch number (useful on restarts)')
parser.add_argument('--evaluate',
                    dest='evaluate',
                    action='store_true',
                    help='evaluate model on validation set')

# Acceleration
parser.add_argument('--ngpu', type=int, default=1, help='0 = CPU')
parser.add_argument('--workers',
                    type=int,
                    default=2,
                    help='number of data loading workers (default: 2)')

# random seed
parser.add_argument('--seed', default=0, type=int, help='manual seed')
parser.add_argument('--add_name', type=str, default='')
parser.add_argument('--log_off', type=str2bool, default=False)
parser.add_argument('--job_id', type=str, default='')


parser.add_argument('--supervision', type=str2bool, default=False, help='whether to use supervision i.e. pretrained models for computing unary saliency measure')
parser.add_argument('--kd', type=str2bool, default=False, help='whether to use knowledge distillation, uses model_t for teacher model')
parser.add_argument('--model_t', type=str, default=None, help='model architecture for computing unary')

#KD related shit
parser.add_argument('--temp', type=float, default=1, help='Temperature for KD')
parser.add_argument('--bce_weight', type=float, default=1, help = 'weightage for the BCE loss')
parser.add_argument('--kl_weight', type=float, default=0.0, help = 'weightage for the KL loss')
parser.add_argument('--pmu', type=float, default=0, help = 'fraction of Batch of mixup images to use')

#mixup batch collater
parser.add_argument('--mixup_batching_strategy', type=str, default='repl', help='replaces clean images with PMU*batch_size clean images')
parser.add_argument('--mixup_batching_sampler', type=str, default='random', help='selects *mixup* images based on certain criteria')

#UNIXkd
parser.add_argument('--strategy', type=int, default=3, help='Stratergy to choose which criteria for uncertainty')
parser.add_argument('--unixkd', type=str2bool, default=False, help="UNIXKD mode --sampling based on uncertainty")
parser.add_argument('--k', required=False, type=int, default=64, help='The number of samples to be selected')
parser.add_argument('--b', required=False, type=int, default=64, help='The centre of the sigmoid function')
parser.add_argument('--w', required=False, type=int, default=1000, help='The width of the sigmoid function')

#optimized mixup
parser.add_argument('--mini_batch_size', type=int, default=4, help='mini batch size for optimized mixup')
parser.add_argument('--alpha_optim', type=float, default=0.1, help='alpha parameter for optimized mixup')
parser.add_argument('--beta_optim', type=float, default=0.1, help='beta parameter for optimized mixup')
parser.add_argument('--strategy_optim', type=int, default=1, help='strategy for optimized mixup')

args = parser.parse_args()
args.use_cuda = args.ngpu > 0 and torch.cuda.is_available()

# random seed
random.seed(args.seed)
np.random.seed(args.seed)
torch.manual_seed(args.seed)
torch.cuda.manual_seed(args.seed)
torch.cuda.manual_seed_all(args.seed)

cudnn.benchmark = True


def experiment_name_non_mnist(dataset=args.dataset,
                              arch=args.arch,
                              epochs=args.epochs,
                              dropout=args.dropout,
                              batch_size=args.batch_size,
                              lr=args.learning_rate,
                              momentum=args.momentum,
                              decay=args.decay,
                              train=args.train,
                              box=args.box,
                              graph=args.graph,
                              beta=args.beta,
                              gamma=args.gamma,
                              eta=args.eta,
                              n_labels=args.n_labels,
                              neigh_size=args.neigh_size,
                              transport=args.transport,
                              t_size=args.t_size,
                              t_eps=args.t_eps,
                              adv_eps=args.adv_eps,
                              adv_p=args.adv_p,
                              in_batch=args.in_batch,
                              mixup_alpha=args.mixup_alpha,
                              job_id=args.job_id,
                              add_name=args.add_name,
                              clean_lam=args.clean_lam,
                              supervision=args.supervision,
                              KD = args.kd,
                              model_t=args.model_t,
                              bce_weight = args.bce_weight,
                              kl_weight = args.kl_weight,
                              seed=args.seed):
    '''
    function for experiment result folder name.
    '''
    
    if KD:
        if args.unixkd:
            exp_name = "UNIXKD_T[{}]_[CE W:{}]_[KL W:{}]_".format(model_t, bce_weight, kl_weight)
        else:
            exp_name = "KD_T[{}]_[CE W:{}]_[KL W:{}]_".format(model_t, bce_weight, kl_weight)
    else:
        exp_name = ""
    exp_name += str(dataset)
    # exp_name += '_BS_' + str(batch_size)
    exp_name += '_arch_' + str(arch)
    exp_name += '_train_' + str(train)
    exp_name += '_eph_' + str(epochs)
    exp_name += '_lr_' + str(lr)
    if mixup_alpha:
        exp_name += '_m_alpha_' + str(mixup_alpha)
    if box:
        exp_name += '_box'
    if graph:
        exp_name += '_graph' + '_n_labels_' + str(n_labels) + '_beta_' + str(
            beta) + '_gamma_' + str(gamma) + '_neigh_' + str(neigh_size) + '_eta_' + str(eta)
    if transport:
        exp_name += '_transport' + '_eps_' + str(t_eps) + '_size_' + str(t_size)
    if adv_p > 0:
        exp_name += '_adv_' + '_eps_' + str(adv_eps) + '_p_' + str(adv_p)
    if in_batch:
        exp_name += '_inbatch'
    if job_id != None:
        exp_name += '_job_id_' + str(job_id)
    if clean_lam > 0:
        exp_name += '_clean_' + str(clean_lam)
    exp_name += '_seed_' + str(seed)
    if add_name != '':
        exp_name += '_add_name_' + str(add_name)
    if supervision:
        exp_name += f'_supervision_[{str(model_t)}]'
    if train not in ['vanilla']:
        exp_name+= '_pmu_[' + str(args.pmu)+"]"

    print('\nexperiment name: ' + exp_name)
    return exp_name


def print_log(print_string, log, end='\n'):
    '''print log'''
    print("{}".format(print_string), end=end)
    if log is not None:
        if end == '\n':
            log.write('{}\n'.format(print_string))
        else:
            log.write('{} '.format(print_string))
        log.flush()


def save_checkpoint(state, is_best, save_path, filename):
    '''save checkpoint'''
    filename = os.path.join(save_path, filename)
    torch.save(state, filename)
    if is_best:
        bestname = os.path.join(save_path, 'model_best.pth.tar')
        shutil.copyfile(filename, bestname)


def adjust_learning_rate(optimizer, epoch, gammas, schedule):
    """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
    lr = args.learning_rate
    assert len(gammas) == len(schedule), "length of gammas and schedule should be equal"
    for (gamma, step) in zip(gammas, schedule):
        if (epoch >= step):
            lr = lr * gamma
        else:
            break
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
    return lr


def accuracy(output, target, topk=(1, )):
    """Computes the precision@k for the specified values of k"""
    maxk = max(topk)
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(target.reshape(1, -1).expand_as(pred))

    res = []
    for k in topk:
        correct_k = correct[:k].reshape(-1).float().sum(0)
        res.append(correct_k.mul_(100.0 / batch_size))
    return res

def kld_loss(out_s, out_t, T):
    log_s_probs = torch.log_softmax(out_s/T, dim=1)
    t_probs = torch.softmax(out_t/T, dim=1)
    return F.kl_div(log_s_probs, t_probs, reduction='batchmean') * T*T


bce_loss = nn.BCELoss().cuda()
bce_loss_sum = nn.BCELoss(reduction='sum').cuda()
softmax = nn.Softmax(dim=1).cuda()
criterion = nn.CrossEntropyLoss().cuda()
criterion_batch = nn.CrossEntropyLoss(reduction='none').cuda()


def train(train_loader, model, optimizer, epoch, args, log, PMU = 0, model_t = None, mp=None):
    '''train given model and dataloader'''
    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()
    mixing_avg = []

    # switch to train mode
    model.train()
    
    # see if model_t is given
    if args.supervision or args.kd:
        model_t.eval()

    end = time.time()
    for i, (input, target) in enumerate(train_loader):
        data_time.update(time.time() - end)
        optimizer.zero_grad()

        input = input.cuda()
        target = target.long().cuda()
        
        if args.unixkd:
            with torch.no_grad():
                student_outputs = model(input)
                probs = torch.nn.functional.softmax(student_outputs, dim=1)
        
                # confidence
                conf = probs.max(dim=1)[0]
                # margin
                rank = torch.argsort(probs, dim=1)
                top2 = torch.gather(probs, dim=1, index=rank[:,-2:])
                margin = top2[:,-1] - top2[:,-2]
                # entropy
                entropy = -torch.sum(probs * torch.log(probs), dim=1)

                if args.strategy == 0:
                    scores = torch.rand(input.size(0)).cuda()
                elif args.strategy == 1:
                    scores = 1 - conf
                elif args.strategy == 2:
                    scores = -margin
                elif args.strategy == 3:
                    scores = entropy
                else: 
                    raise ValueError('Invalid strategy.')
                
                rank = torch.argsort(scores, descending=True)
                
                r = torch.arange(input.size(0)).float()
                m = (2*args.b-1) / (2*args.batch_size)
                mask_proto = 1 / (1 + torch.exp(-args.w * (r/args.batch_size - m) ))
                mask_proto = mask_proto.to('cuda')
                    
            # sort the inputs based on ranking
            input = input[rank]
            target = target[rank]

        
        unary = None
        noise = None
        adv_mask1 = 0
        adv_mask2 = 0

        # train with clean images
        if args.train == 'vanilla':
            input_var, target_var = Variable(input), Variable(target)
            if args.kd:
                output, reweighted_target, teacher_logits = model(input_var, target_var, model_t = model_t)
                loss = args.bce_weight*bce_loss(softmax(output), reweighted_target) + args.kl_weight*kld_loss(out_s=output, out_t=teacher_logits, T=args.temp)
            else:
                output, reweighted_target = model(input_var, target_var)
                loss = bce_loss(softmax(output), reweighted_target)
                
        #! train with optimized mixup images
        
        elif args.train == 'optim_mix':
            input_var, target_var = Variable(input), Variable(target)
            # TODO: Add student uncertainties here 
            with torch.no_grad():
                student_outputs = model(input_var)
                probs = torch.nn.functional.softmax(student_outputs, dim=1)
                
                if args.strategy_optim == 1:
                    scores = probs.max(dim=1)[0] # compute the confidence
                elif args.strategy_optim == 2:
                    rank = torch.argsort(probs, dim=1)
                    top2 = torch.gather(probs, dim=1, index=rank[:,-2:])
                    scores = top2[:,-1] - top2[:,-2] # compute the margin
                elif args.strategy_optim == 3:
                    scores = -torch.sum(probs * torch.log(probs), dim=1) # computes the entropy
                else: 
                    raise ValueError('Invalid strategy.')
            # TODO: pass the uncertainties to the model and optimize the mixup images
            scores = scores.cpu().numpy()
            indices = list(range(input_var.shape[0])) 
            random.shuffle(indices)
            groups = [indices[i:i + args.mini_batch_size] for i in range(0, len(indices), args.mini_batch_size)]
            # Initialize a large Z matrix of zeros
            big_Z = torch.zeros((input_var.shape[0], input_var.shape[0])).cuda()
            # Fill big_Z with smaller Z matrices on its diagonal according to the shuffled indices
            for group in groups:
                mix_z = z_optimizer(args.mini_batch_size, args.mini_batch_size)(scores[group], alpha=args.alpha_optim, beta=args.beta_optim, print_message=False)
                for i, row in enumerate(group):
                    for j, col in enumerate(group):
                        big_Z[row, col] = mix_z[i, j]
            
            reweighted_target = to_one_hot(target_var, args.num_classes)
            batch_size, channel, height, width = input_var.shape
            flattened_input = input_var.view(batch_size, -1)
            flattened_input, reweighted_target = big_Z@flattened_input, big_Z@reweighted_target # alterting the images
            input_var = Variable(flattened_input.view(batch_size, channel, height, width), requires_grad=True)
            
            output= model(input_var)
            loss = bce_loss(softmax(output), reweighted_target)

        # train with mixup images
        elif args.train == 'mixup':
            # process for Puzzle Mix
            if args.graph:
                # whether to add adversarial noise or not
                if args.adv_p > 0:
                    adv_mask1 = np.random.binomial(n=1, p=args.adv_p)
                    adv_mask2 = np.random.binomial(n=1, p=args.adv_p)
                else:
                    adv_mask1 = 0
                    adv_mask2 = 0

                # random start
                if (adv_mask1 == 1 or adv_mask2 == 1):
                    noise = torch.zeros_like(input).uniform_(-args.adv_eps / 255.,
                                                             args.adv_eps / 255.)
                    input_orig = input * args.std + args.mean
                    input_noise = input_orig + noise
                    input_noise = torch.clamp(input_noise, 0, 1)
                    noise = input_noise - input_orig
                    input_noise = (input_noise - args.mean) / args.std
                    input_var = Variable(input_noise, requires_grad=True)
                else:
                    input_var = Variable(input, requires_grad=True)
                target_var = Variable(target)

                # calculate saliency (unary)
                if args.clean_lam == 0:
                    if args.supervision:
                        model_t.eval()
                        output_t = model_t(input_var)
                        loss_batch = criterion_batch(output_t, target_var)
                    else:
                        model.eval()
                        output = model(input_var)
                        loss_batch = criterion_batch(output, target_var)
                else:
                    if args.supervision:
                        model_t.train()
                        output_t = model_t(input_var)
                        loss_batch = 2 * args.clean_lam * criterion_batch(output_t,
                                                                          target_var) / args.num_classes
                    else:
                        model.train()
                        output = model(input_var)
                        loss_batch = 2 * args.clean_lam * criterion_batch(output,
                                                                        target_var) / args.num_classes

                loss_batch_mean = torch.mean(loss_batch, dim=0)
                loss_batch_mean.backward(retain_graph=True)

                unary = torch.sqrt(torch.mean(input_var.grad**2, dim=1))

                # calculate adversarial noise
                if (adv_mask1 == 1 or adv_mask2 == 1):
                    noise += (args.adv_eps + 2) / 255. * input_var.grad.sign()
                    noise = torch.clamp(noise, -args.adv_eps / 255., args.adv_eps / 255.)
                    adv_mix_coef = np.random.uniform(0, 1)
                    noise = adv_mix_coef * noise

                if args.clean_lam == 0:
                    model.train()
                    optimizer.zero_grad()

            input_var, target_var = Variable(input), Variable(target)
            # perform mixup and calculate loss
            # output, reweighted_target = model(input_var,
            #                                   target_var,
            #                                   mixup=True,
            #                                   args=args,
            #                                   grad=unary,
            #                                   noise=noise,
            #                                   adv_mask1=adv_mask1,
            #                                   adv_mask2=adv_mask2,
            #                                   mp=mp)
            
            # perform mixup and calculate loss
            if args.kd:
                output, reweighted_target, teacher_logits = model(input_var,
                                                                target_var,
                                                                mixup=True,
                                                                args=args,
                                                                grad=unary,
                                                                noise=noise,
                                                                adv_mask1=adv_mask1,
                                                                adv_mask2=adv_mask2,
                                                                mp=mp,
                                                                PMU = PMU,
                                                                model_t=model_t)
                loss = args.bce_weight*bce_loss(softmax(output), reweighted_target) + args.kl_weight*kld_loss(out_s=output, out_t=teacher_logits, T=args.temp)
            else:
                output, reweighted_target =  model(input_var,
                                                    target_var,
                                                    mixup=True,
                                                    args=args,
                                                    grad=unary,
                                                    noise=noise,
                                                    adv_mask1=adv_mask1,
                                                    adv_mask2=adv_mask2,
                                                    mp=mp)
                loss = bce_loss(softmax(output), reweighted_target)

        # for manifold mixup
        elif args.train == 'mixup_hidden':
            input_var, target_var = Variable(input), Variable(target)
            output, reweighted_target = model(input_var, target_var, mixup_hidden=True, args=args)
            loss = bce_loss(softmax(output), reweighted_target)
        else:
            raise AssertionError('wrong train type!!')

        # measure accuracy and record loss
        if args.unixkd:
            PMU = int(PMU) # convert it to integer for slicing
            target = target[:PMU]
        prec1, prec5 = accuracy(output, target, topk=(1, 5))
        losses.update(loss.item(), input.size(0))
        top1.update(prec1.item(), input.size(0))
        top5.update(prec5.item(), input.size(0))

        # compute gradient and do SGD step
        loss.backward()
        optimizer.step()

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

    print_log(
        '  **Train** Prec@1 {top1.avg:.3f} Prec@5 {top5.avg:.3f} Error@1 {error1:.3f}'.format(
            top1=top1, top5=top5, error1=100 - top1.avg), log)
    return top1.avg, top5.avg, losses.avg


def validate(val_loader, model, log, fgsm=False, eps=4, rand_init=False, mean=None, std=None):
    '''evaluate trained model'''
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()

    # switch to evaluate mode
    model.eval()

    for i, (input, target) in enumerate(val_loader):
        if args.use_cuda:
            input = input.cuda()
            target = target.cuda()

        # check FGSM for adversarial training
        if fgsm:
            input_var = Variable(input, requires_grad=True)
            target_var = Variable(target)

            optimizer_input = torch.optim.SGD([input_var], lr=0.1)
            output = model(input_var)
            loss = criterion(output, target_var)
            optimizer_input.zero_grad()
            loss.backward()

            sign_data_grad = input_var.grad.sign()
            input = input * std + mean + eps / 255. * sign_data_grad
            input = torch.clamp(input, 0, 1)
            input = (input - mean) / std

        with torch.no_grad():
            input_var = Variable(input)
            target_var = Variable(target)

            # compute output
            output = model(input_var)
            loss = criterion(output, target_var)

        # measure accuracy and record loss
        prec1, prec5 = accuracy(output.data, target, topk=(1, 5))
        losses.update(loss.item(), input.size(0))
        top1.update(prec1.item(), input.size(0))
        top5.update(prec5.item(), input.size(0))

    if fgsm:
        print_log('Attack (eps : {}) Prec@1 {top1.avg:.2f}'.format(eps, top1=top1), log)
    else:
        print_log(
            '  **Test** Prec@1 {top1.avg:.3f} Prec@5 {top5.avg:.3f} Error@1 {error1:.3f} Loss: {losses.avg:.3f} '
            .format(top1=top1, top5=top5, error1=100 - top1.avg, losses=losses), log)
    return top1.avg, losses.avg


best_acc = 0

def print_available_cuda_devices():
    if torch.cuda.is_available():
        num_devices = torch.cuda.device_count()
        print(f"Number of available CUDA devices: {num_devices}")
        for i in range(num_devices):
            print(f"Device {i}: {torch.cuda.get_device_name(i)}")
    else:
        print("No CUDA devices available.")
        
def main():
    # set up the experiment directories
    
    print_available_cuda_devices()
    
    if not args.log_off:
        exp_name = experiment_name_non_mnist()
        exp_dir = os.path.join(args.root_dir, exp_name)

        if not os.path.exists(exp_dir):
            os.makedirs(exp_dir)

        copy_script_to_folder(os.path.abspath(__file__), exp_dir)

        result_png_path = os.path.join(exp_dir, 'results.png')
        log = open(os.path.join(exp_dir, 'log.txt'.format(args.seed)), 'w')
        print_log('save path : {}'.format(exp_dir), log)
    else:
        log = None

    global best_acc

    state = {k: v for k, v in args._get_kwargs()}
    print("")
    print_log(state, log)
    print("")
    print_log("Random Seed: {}".format(args.seed), log)
    print_log("python version : {}".format(sys.version.replace('\n', ' ')), log)
    print_log("torch  version : {}".format(torch.__version__), log)
    print_log("cudnn  version : {}".format(torch.backends.cudnn.version()), log)

    # dataloader
    train_loader, valid_loader, _, test_loader, num_classes = load_data_subset(
        args.batch_size,
        2,
        args.dataset,
        args.data_dir,
        labels_per_class=args.labels_per_class,
        valid_labels_per_class=args.valid_labels_per_class,
        mixup_alpha=args.mixup_alpha)

    if args.dataset == 'tiny-imagenet-200':
        stride = 2
        args.mean = torch.tensor([0.5] * 3, dtype=torch.float32).reshape(1, 3, 1, 1).cuda()
        args.std = torch.tensor([0.5] * 3, dtype=torch.float32).reshape(1, 3, 1, 1).cuda()
        args.labels_per_class = 500
    elif args.dataset == 'cifar10':
        stride = 1
        args.mean = torch.tensor([x / 255 for x in [125.3, 123.0, 113.9]],
                                 dtype=torch.float32).reshape(1, 3, 1, 1).cuda()
        args.std = torch.tensor([x / 255 for x in [63.0, 62.1, 66.7]],
                                dtype=torch.float32).reshape(1, 3, 1, 1).cuda()
        args.labels_per_class = 5000
    elif args.dataset == 'cifar100':
        stride = 1
        args.mean = torch.tensor([x / 255 for x in [129.3, 124.1, 112.4]],
                                 dtype=torch.float32).reshape(1, 3, 1, 1).cuda()
        args.std = torch.tensor([x / 255 for x in [68.2, 65.4, 70.4]],
                                dtype=torch.float32).reshape(1, 3, 1, 1).cuda()
        args.labels_per_class = 500
    else:
        raise AssertionError('Given Dataset is not supported!')

    # create model
    print_log("=> creating model '{}'".format(args.arch), log)
    #net = models.__dict__[args.arch](num_classes, args.dropout, stride).cuda()
    net = models.__dict__[args.arch](num_classes=num_classes).cuda()
    args.num_classes = num_classes

    net = torch.nn.DataParallel(net, device_ids=list(range(args.ngpu)))
    optimizer = torch.optim.SGD(net.parameters(),
                                state['learning_rate'],
                                momentum=state['momentum'],
                                weight_decay=state['decay'],
                                nesterov=True)

    recorder = RecorderMeter(args.epochs)
    
    # loading the teacher supervision model
    if args.supervision or args.kd:
        print_log("=> loading teacher model '{}'".format(args.model_t), log)
        model_t = models.__dict__[args.model_t](num_classes=num_classes).cuda()
        model_t.load_state_dict(torch.load('./pretrained_checkpoint/{}/ckpt/best.pth'.format(args.model_t))['state_dict'])
        model_t = torch.nn.DataParallel(model_t, device_ids=list(range(args.ngpu)))
        model_t.eval()
        
        _, _ = validate(test_loader, model_t, log)
    else:
        print_log("=> not using KD or supervision mode so *NO* teacher model loaded!", log)
        model_t = None
        
    # optionally resume from a checkpoint
    if args.resume:
        if os.path.isfile(args.resume):
            print_log("=> loading checkpoint '{}'".format(args.resume), log)
            checkpoint = torch.load(args.resume)
            recorder = checkpoint['recorder']
            args.start_epoch = checkpoint['epoch']
            net.load_state_dict(checkpoint['state_dict'])
            optimizer.load_state_dict(checkpoint['optimizer'])
            best_acc = recorder.max_accuracy(False)
            print_log(
                "=> loaded checkpoint '{}' accuracy={} (epoch {})".format(
                    args.resume, best_acc, checkpoint['epoch']), log)
        else:
            print_log("=> no checkpoint found at '{}'".format(args.resume), log)
    else:
        print_log("=> do not use any checkpoint for {} model".format(args.arch), log)

    if args.evaluate:
        validate(test_loader, net, criterion, log)
        return

    if args.mp > 0:
        mp = Pool(args.mp)
    else:
        mp = None

    start_time = time.time()
    epoch_time = AverageMeter()
    train_loss = []
    train_acc = []
    test_loss = []
    test_acc = []

    for epoch in range(args.start_epoch, args.epochs):
        current_learning_rate = adjust_learning_rate(optimizer, epoch, args.gammas, args.schedule)
        if epoch == args.schedule[0]:
            args.clean_lam == 0

        need_hour, need_mins, need_secs = convert_secs2time(epoch_time.avg * (args.epochs - epoch))
        need_time = '[Need: {:02d}:{:02d}:{:02d}]'.format(need_hour, need_mins, need_secs)
        print_log('\n==>>{:s} [Epoch={:03d}/{:03d}] {:s} [learning_rate={:.16e}]'.format(time_string(), epoch, args.epochs, need_time, current_learning_rate) \
                + ' [Best : Accuracy={:.2f}, Error={:.2f}]'.format(recorder.max_accuracy(False), 100-recorder.max_accuracy(False)), log)

        # train for one epoch
        tr_acc, tr_acc5, tr_los = train(train_loader, net, optimizer, epoch, args, log, model_t = model_t, mp=mp, PMU = args.pmu)

        # evaluate on validation set
        val_acc, val_los = validate(test_loader, net, log)
        if (epoch % 50) == 0 and args.adv_p > 0:
            _, _ = validate(test_loader, net, log, fgsm=True, eps=4, mean=args.mean, std=args.std)
            _, _ = validate(test_loader, net, log, fgsm=True, eps=8, mean=args.mean, std=args.std)

        train_loss.append(tr_los)
        train_acc.append(tr_acc)
        test_loss.append(val_los)
        test_acc.append(val_acc)

        is_best = False
        if val_acc > best_acc:
            is_best = True
            best_acc = val_acc

        # measure elapsed time
        epoch_time.update(time.time() - start_time)
        start_time = time.time()

        if args.log_off:
            continue

        # save log
        save_checkpoint(
            {
                'epoch': epoch + 1,
                'arch': args.arch,
                'state_dict': net.state_dict(),
                'recorder': recorder,
                'optimizer': optimizer.state_dict(),
            }, is_best, exp_dir, 'checkpoint.pth.tar')

        dummy = recorder.update(epoch, tr_los, tr_acc, val_los, val_acc)
        if (epoch + 1) % 100 == 0:
            recorder.plot_curve(result_png_path)

        train_log = OrderedDict()
        train_log['train_loss'] = train_loss
        train_log['train_acc'] = train_acc
        train_log['test_loss'] = test_loss
        train_log['test_acc'] = test_acc

        pickle.dump(train_log, open(os.path.join(exp_dir, 'log.pkl'), 'wb'))
        plotting(exp_dir)

    acc_var = np.maximum(
        np.max(test_acc[-10:]) - np.median(test_acc[-10:]),
        np.median(test_acc[-10:]) - np.min(test_acc[-10:]))
    print_log(
        "\nfinal 10 epoch acc (median) : {:.2f} (+- {:.2f})".format(np.median(test_acc[-10:]),
                                                                    acc_var), log)

    if not args.log_off:
        log.close()


if __name__ == '__main__':
    main()

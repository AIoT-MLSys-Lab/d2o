#!/bin/bash

#SBATCH --job-name=2_7B_m005_015      # 作业名称
#SBATCH --account=PAS2473		    # Project ID
#SBATCH --output=/users/PAS2473/brucewan666/Efficient_LLMs/LLM_merge_new/new_output_logs/2_7B_m005_015.log         # 输出日志文件
#SBATCH --error=/users/PAS2473/brucewan666/Efficient_LLMs/LLM_merge_new/new_output_logs/2_7B_m005_015_error.log          # 错误日志文件
#SBATCH --nodes=1                   # 节点数
#SBATCH --ntasks-per-node=1         # 每个节点的任务数
#SBATCH --cpus-per-task=4           # 每个任务使用的 CPU 核心数
#SBATCH --gpus-per-node=1	        # GPU per node
#SBATCH --mem=80G                  # 内存限制
#SBATCH --time=20:00:00             # 作业运行时间限制

# 运行命令或脚本 wget https://repo.anaconda.com/archive/Anaconda3-2023.07-2-Linux-x86_64.sh
source $HOME/anaconda3/bin/activate /users/PAS2473/brucewan666/anaconda3/envs/kivi
# module load cuda 
CUDA_VISIBLE_DEVICES=0 python /users/PAS2473/brucewan666/Efficient_LLMs/LLM_merge_new/run_pred_long_bench.py --model_name_or_path meta-llama/Llama-2-7b-hf \
    --cache_dir /fs/scratch/PAS2473/zhongwei_models \
    --use_real_merge True \
    --model_type llama \
    --hh_ratio 0.05 \
    --recent_ratio 0.15 \
    --action_name merge_llama2_7b_005_015 \
    --e True 

python /users/PAS2473/brucewan666/Efficient_LLMs/LLM_merge_new/eval_long_bench.py --model Llama-2-7b-hf_merge_llama2_7b_005_015 --e 

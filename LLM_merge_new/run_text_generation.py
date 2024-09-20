#!/usr/bin/env python
# coding=utf-8
# Copyright 2018 Google AI, Google Brain and Carnegie Mellon University Authors and the HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Conditional text generation with the auto-regressive models
"""


import argparse
import logging

import numpy as np
import torch
import json
import tqdm 
import copy 

from transformers import (
    CTRLLMHeadModel,
    CTRLTokenizer,
    GPT2LMHeadModel,
    GPT2Tokenizer,
    OpenAIGPTLMHeadModel,
    OpenAIGPTTokenizer,
    TransfoXLLMHeadModel,
    TransfoXLTokenizer,
    XLMTokenizer,
    XLMWithLMHeadModel,
    XLNetLMHeadModel,
    XLNetTokenizer,
)

from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig

from not_real_drop_hh.modify_llama import convert_kvcache_llama_heavy_recent, LlamaAttention_heavy_hitter
# from utils_hh.modify_gptneox import convert_kvcache_gpt_neox_heavy_recent, GPTNeoXAttention_Mask
# from utils_hh.modify_opt import convert_kvcache_opt_heavy_recent, OPTAttention_Mask
from kv_token_merge import modify_llama_merge
from kv_token_merge.modify_llama_merge import H2OLlamaForCausalLM_streaming
# from kv_token_merge.modify_llama import H2OLlamaForCausalLM_streaming


import  time

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_LENGTH = int(10000)  # Hardcoded max length to avoid infinite loop

MODEL_CLASSES = {
    "gpt2": (GPT2LMHeadModel, GPT2Tokenizer),
    "ctrl": (CTRLLMHeadModel, CTRLTokenizer),
    "openai-gpt": (OpenAIGPTLMHeadModel, OpenAIGPTTokenizer),
    "xlnet": (XLNetLMHeadModel, XLNetTokenizer),
    "transfo-xl": (TransfoXLLMHeadModel, TransfoXLTokenizer),
    "xlm": (XLMWithLMHeadModel, XLMTokenizer),
}

# Padding text to help Transformer-XL and XLNet with short prompts as proposed by Aman Rusia
# in https://github.com/rusiaaman/XLNet-gen#methodology
# and https://medium.com/@amanrusia/xlnet-speaks-comparison-to-gpt-2-ea1a4e9ba39e
PREFIX = """In 1991, the remains of Russian Tsar Nicholas II and his family
(except for Alexei and Maria) are discovered.
The voice of Nicholas's young son, Tsarevich Alexei Nikolaevich, narrates the
remainder of the story. 1883 Western Siberia,
a young Grigori Rasputin is asked by his father and a group of men to perform magic.
Rasputin has a vision and denounces one of the men as a horse thief. Although his
father initially slaps him for making such an accusation, Rasputin watches as the
man is chased outside and beaten. Twenty years later, Rasputin sees a vision of
the Virgin Mary, prompting him to become a priest. Rasputin quickly becomes famous,
with people, even a bishop, begging for his blessing. <eod> </s> <eos>"""


def set_seed(args):
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if args.n_gpu > 0:
        torch.cuda.manual_seed_all(args.seed)


ENABLE_Heavy_Hitter_FUNCTIONS = {
    "llama": convert_kvcache_llama_heavy_recent,
    # "opt": convert_kvcache_opt_heavy_recent,
    # "gpt_neox": convert_kvcache_gpt_neox_heavy_recent,
}


def main():

    """
     CUDA_VISIBLE_DEVICES=0 python  run_text_generation.py --model_arch llama --model_name meta-llama/Llama-2-7b-chat-hf --recent_size 240 --heavy_hitter_size  16 
    
    """
    parser = argparse.ArgumentParser()

    parser.add_argument("--model_arch", type=str, default='llama')
    parser.add_argument("--model_name", type=str, default='meta-llama/Llama-2-7b-chat-hf')
    parser.add_argument("--cache_dir", type=str, default='/local/scratch0/data_and_checkpoint/models')

    parser.add_argument("--heavy_ratio", type=float, default=0.1)
    parser.add_argument("--recent_ratio", type=float, default=0.1)
    parser.add_argument("--heavy_hitter_size", type=int, default=1)
    parser.add_argument("--recent_size", type=int, default=255)

    parser.add_argument("--length", type=int, default=10000)

    parser.add_argument("--seed", type=int, default=42, help="random seed for initialization")
    parser.add_argument("--no_cuda", action="store_true", help="Avoid using CUDA when available")
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Whether to use 16-bit (mixed) precision (through NVIDIA apex) instead of 32-bit",
    )
    args = parser.parse_args()

    args.device = torch.device("cuda" if torch.cuda.is_available() and not args.no_cuda else "cpu")
    args.n_gpu = 0 if args.no_cuda else torch.cuda.device_count()

    logger.warning(f"device: {args.device}, n_gpu: {args.n_gpu}, 16-bits training: {args.fp16}")
    set_seed(args)

    # Change to your custom prompt text
    # prompt_text = 'In the year 2087, humanity has achieved remarkable technological advancements and established colonies on multiple planets within the Milky Way galaxy. Interstellar travel has become commonplace, with faster-than-light spacecraft enabling people to explore distant star systems. Earth has undergone significant changes due to sustainable development efforts, such as harnessing renewable energy sources and implementing widespread ecological restoration projects. However, alongside these triumphs, new challenges have emerged, including the rise of artificial intelligence, ethical dilemmas surrounding genetic engineering, and interplanetary political tensions. Against this backdrop, a team of intrepid scientists embarks on a mission to uncover the secrets of an ancient alien civilization, hidden deep within an uncharted exoplanet. As they navigate treacherous terrains and encounter otherworldly phenomena, they must confront their own fears and reconcile humanity\'s thirst for knowledge with the potential consequences of uncovering secrets that were better left buried. The fate of both their mission and the future of humanity hang in the balance.'
    prompt_text = 'Southern University of Science and technology is '

    model_name = args.model_name
    config = AutoConfig.from_pretrained(model_name, cache_dir=args.cache_dir)

    config.heavy_ratio = args.heavy_ratio  # seting the ratio here
    config.recent_ratio = args.recent_ratio 

    config.hh_size = args.heavy_hitter_size
    config.recent_size = args.recent_size

    
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True, cache_dir=args.cache_dir)

    ######## Generate with Full Cache
    model = AutoModelForCausalLM.from_pretrained(model_name, cache_dir=args.cache_dir)
    model.half().eval().cuda()

    # input_ids = tokenizer(prompt_text, return_tensors='pt').input_ids.to(model.device)
    input_ids = tokenizer(prompt_text, add_special_tokens=False, return_tensors='pt').input_ids.to(model.device)

    full_start_time = time.time()

    generate_ids = model.generate(input_ids, max_new_tokens=1000)
    result = tokenizer.batch_decode(generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
    print("################## Generated Context with Full Cache ###################")
    print(result)
    print('Full cache time:', time.time() - full_start_time)


    ######## Enable HH
    # checkpoint = copy.deepcopy(model.state_dict())
    # model = ENABLE_Heavy_Hitter_FUNCTIONS[args.model_arch](model, config)
    # model.load_state_dict(checkpoint)
    # model.half().eval().cuda()


    ################## using real drop or merge instead of mask #########################


    model = H2OLlamaForCausalLM_streaming.from_pretrained(
        args.model_name,
        device_map="auto",
        config=config,
        torch_dtype=torch.float16,
        trust_remote_code=True,
        cache_dir = args.cache_dir
    )

    model.half().eval().cuda()

    merge_start_time = time.time()
    generate_ids_hh = model.generate(input_ids, max_new_tokens=1000)
    result_hh = tokenizer.batch_decode(generate_ids_hh, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
    print("################## Generated Context with Heavy Hitter Oracle ###################")
    print(result_hh)
    print('Merge cache time: ', time.time() - merge_start_time)


if __name__ == "__main__":
    main()
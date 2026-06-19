# Medical Phi-3 LoRA Adapter

This folder contains the LoRA adapter fine-tuned from:

Base model:
microsoft/Phi-3-mini-4k-instruct

Training dataset:
ruslanmv/HealthCareMagic-100k

Use this adapter with Hugging Face Transformers + PEFT.
Do not load it alone as a full model. Load the base model first, then attach this adapter.

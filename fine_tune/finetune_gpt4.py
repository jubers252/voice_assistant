#!/usr/bin/env python3
"""
Fine-tuning script for GPT-4.1-nano model with Sofi voice assistant tools.

This module handles the complete fine-tuning workflow:
1. Validates training data format
2. Uploads data to OpenAI
3. Creates and monitors fine-tuning jobs
4. Returns fine-tuned model identifier

Usage:
    python finetune_gpt4nano.py

Requirements:
    - OPENAI_API_KEY environment variable or .env file
    - Training data in JSONL format
"""

import os
import sys
import json
import time
from pathlib import Path
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def load_config():
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("OPENAI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"\'')
                        break
    
    if not api_key:
        print("Error: OPENAI_API_KEY not found")
        print('Set it as: export OPENAI_API_KEY="sk-..." or create .env file')
        sys.exit(1)
    
    return api_key


def validate_training_file(filepath):
    print(f"Validating {filepath}...")
    
    if not Path(filepath).exists():
        print(f"Error: File not found: {filepath}")
        return False
    
    valid_count = 0
    errors = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "messages" not in data:
                    errors.append(f"Line {line_num}: Missing 'messages' key")
                elif len(data["messages"]) < 2:
                    errors.append(f"Line {line_num}: Need at least 2 messages")
                else:
                    valid_count += 1
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Invalid JSON - {e}")
    
    if errors:
        print(f"Found {len(errors)} errors:")
        for error in errors[:5]:
            print(f"  {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors)-5} more")
        return False
    
    print(f"Validation passed: {valid_count} training examples")
    return True


def upload_training_file(client, filepath):
    print(f"\nUploading {filepath}...")
    
    try:
        with open(filepath, 'rb') as f:
            response = client.files.create(
                file=f,
                purpose='fine-tune'
            )
        
        print(f"File uploaded successfully")
        print(f"  File ID: {response.id}")
        print(f"  Size: {response.bytes} bytes")
        return response.id
    except Exception as e:
        print(f"Upload failed: {e}")
        return None


def create_fine_tune_job(client, file_id, model="gpt-4.1-nano", suffix=None):
    print(f"\nCreating fine-tune job...")
    print(f"  Base model: {model}")
    
    try:
        params = {"training_file": file_id, "model": model}
        if suffix:
            params["suffix"] = suffix
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M")
            params["suffix"] = f"sofi-{timestamp}"
        
        response = client.fine_tuning.jobs.create(**params)
        print(f"Fine-tune job created")
        print(f"  Job ID: {response.id}")
        print(f"  Status: {response.status}")
        return response
    except Exception as e:
        print(f"Job creation failed: {e}")
        return None


def monitor_fine_tune_job(client, job_id):
    print(f"\nMonitoring job {job_id}...")
    print("This may take 10-30 minutes depending on dataset size\n")
    
    last_status = None
    
    try:
        while True:
            job = client.fine_tuning.jobs.retrieve(job_id)
            
            if job.status != last_status:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] Status: {job.status}")
                last_status = job.status
            
            if job.status == "succeeded":
                print("\nFine-tuning completed successfully!")
                print(f"Fine-tuned model: {job.fine_tuned_model}")
                return job.fine_tuned_model
                
            elif job.status == "failed":
                print("\nFine-tuning failed!")
                if job.error:
                    print(f"Error: {job.error}")
                return None
                
            elif job.status == "cancelled":
                print("\nFine-tuning was cancelled")
                return None
            
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring interrupted. Job continues in background.")
        print(f"Check status: https://platform.openai.com/finetune/{job_id}")
        return None
    except Exception as e:
        print(f"\nMonitoring error: {e}")
        return None


def list_fine_tune_jobs(client, limit=5):
    print("\nRecent fine-tune jobs:")
    
    try:
        jobs = client.fine_tuning.jobs.list(limit=limit)
        for job in jobs.data:
            print(f"\n  Job ID: {job.id}")
            print(f"  Status: {job.status}")
            print(f"  Model: {job.model}")
            if job.fine_tuned_model:
                print(f"  Fine-tuned: {job.fine_tuned_model}")
            print(f"  Created: {datetime.fromtimestamp(job.created_at)}")
    except Exception as e:
        print(f"  Error listing jobs: {e}")


def main():
    print("=" * 60)
    print("  Model Fine-tuning for Sofi Voice Assistant (GPT-4.1-nano)")
    print("=" * 60)
    print()
    
    api_key = load_config()
    client = OpenAI(api_key=api_key)
    
    training_file = "fine_tune/sofi_comprehensive_training.jsonl"
    base_model = "gpt-4.1-nano-2025-04-14"
    
    # Locate training file
    if not Path(training_file).exists() and Path("sofi_500_samples_fixed.jsonl").exists():
        print(f"Note: {training_file} not found")
        print(f"Using: sofi_500_samples_fixed.jsonl instead\n")
        training_file = "sofi_500_samples_fixed.jsonl"
    elif not Path(training_file).exists() and Path("sofi_500_samples.jsonl").exists():
        print(f"Note: {training_file} not found")
        response = input("Use sofi_500_samples.jsonl? (y/N): ")
        if response.lower() == 'y':
            training_file = "sofi_500_samples.jsonl"
        else:
            sys.exit(1)
    elif not Path(training_file).exists():
        print(f"Error: No training file found!")
        sys.exit(1)
    
    if not validate_training_file(training_file):
        print("\nValidation failed. Please fix errors and try again.")
        sys.exit(1)
    
    print("\nConfiguration:")
    print(f"  Training file: {training_file}")
    print(f"  Base model: {base_model}")
    print()
    
    response = input("Proceed with fine-tuning? (y/N): ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    file_id = upload_training_file(client, training_file)
    if not file_id:
        sys.exit(1)
    
    job = create_fine_tune_job(client, file_id, model=base_model)
    if not job:
        sys.exit(1)
    
    fine_tuned_model = monitor_fine_tune_job(client, job.id)
    
    if fine_tuned_model:
        print(f"\nSave this model name: {fine_tuned_model}")
        
    list_fine_tune_jobs(client)
    
    print()
    print("=" * 60)
    print("For more details: https://platform.openai.com/finetune")
    print("=" * 60)


if __name__ == "__main__":
    main()

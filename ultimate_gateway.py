import os
import subprocess
import sys
import time

def run_command(command, description):
    print(f"\n[+] {description}")
    try:
        subprocess.run(command, check=True, shell=True)
    except subprocess.CalledProcessError:
        print(f"[-] Error executing: {command}")
        print("Please ensure Python and Ollama are properly installed.")
        sys.exit(1)

# Step 1: Install Required Libraries
run_command("pip install -q litellm[proxy] python-dotenv openai", "Installing required Python packages...")

# Step 2: Auto-Generate the .env File (if it doesn't exist)
env_content = """# Replace these placeholders with your actual API keys
GEMINI_API_KEY=your_google_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
"""
if not os.path.exists(".env"):
    with open(".env", "w") as f:
        f.write(env_content)
    print("[+] Created .env file. Add your real API keys to this file later.")
else:
    print("[+] .env file already exists. Skipping creation.")

# Step 3: Auto-Generate the LiteLLM config.yaml
yaml_content = """model_list:
  # --- CLOUD API MODELS ---
  - model_name: gemini-flash
    litellm_params:
      model: gemini/gemini-1.5-flash
      api_key: "os.environ/GEMINI_API_KEY"

  - model_name: deepseek-cloud
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: "os.environ/DEEPSEEK_API_KEY"

  # --- OFFLINE OPEN SOURCE MODELS ---
  - model_name: local-deepseek
    litellm_params:
      model: ollama/deepseek-r1:8b
      api_base: http://localhost:11434

  - model_name: local-llama
    litellm_params:
      model: ollama/llama3.1:8b
      api_base: http://localhost:11434
"""
with open("config.yaml", "w") as f:
    f.write(yaml_content)
print("[+] Created config.yaml file.")

# Step 4: Download Open-Source Models
models = ["deepseek-r1:8b", "llama3.1:8b"]
for model in models:
    print(f"\n[+] Downloading {model} to your hard drive (This may take several minutes)...")
    subprocess.run(f"ollama pull {model}", shell=True)

# Step 5: Boot Up the Unified Gateway
print("\n[+] Setup complete! Starting the Unified AI Gateway on http://localhost:4000/v1 ...")
print("[!] Keep this terminal window open. To stop the server, press Ctrl+C.")
time.sleep(2)

try:
    subprocess.run("litellm --config config.yaml --port 4000", shell=True)
except KeyboardInterrupt:
    print("\n[+] Gateway stopped safely.")
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash")
GATEWAY_KEY = os.getenv("LITELLM_MASTER_KEY")

# Connect the client to your custom LiteLLM Gateway
client = OpenAI(
    api_key=GATEWAY_KEY,
    base_url="http://localhost:4000/v1"
)

def evaluate_job(job_title, job_description):
    prompt = f"""
    Evaluate this job posting for an AWS Cloud Support / DevOps role.
    Job Title: {job_title}
    Description: {job_description}
    Return a score from 1-100 based on match quality.
    """
    
    try:
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert IT career coach."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=200
        )
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error evaluating {job_title}: {str(e)}")
        return None

if __name__ == "__main__":
    print("Testing Job Evaluator against local gateway...")
    score = evaluate_job("Cloud Support Engineer AWS", "Requires AWS, Terraform, and Linux administration.")
    print("\nResult:", score)
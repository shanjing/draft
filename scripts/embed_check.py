import os
from pathlib import Path
import click
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from dotenv import load_dotenv

# Load .env from the repo root (one level up from scripts/)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Mean Pooling logic
def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output[0] 
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('-s', '--sentence', 'sentences', multiple=True, required=True, 
              help='Sentence to encode. Use multiple times for batch processing.')
def inspect_embeddings(sentences):
    """Utility to examine embeddings using all-MiniLM-L6-v2."""
    
    # Retrieve the token with a null fallback
    hf_token = os.getenv("HF_API_KEY")
    auth_status = "Authenticated (HF_API_KEY)" if hf_token else "Visitor (Unauthenticated)"
    
    click.secho(f"🚀 Status: {auth_status}", fg='blue')
    click.secho(f"📦 Loading model for {len(sentences)} sentences...", fg='cyan')

    model_id = 'sentence-transformers/all-MiniLM-L6-v2'
    
    # Load with optional token
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)
    model = AutoModel.from_pretrained(model_id, token=hf_token)

    encoded_input = tokenizer(list(sentences), padding=True, truncation=True, return_tensors='pt')

    with torch.no_grad():
        model_output = model(**encoded_input)

    sentence_embeddings = mean_pooling(model_output, encoded_input['attention_mask'])
    sentence_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)

    click.echo("\n" + click.style("--- Tensor Metadata ---", bold=True, fg='yellow'))
    click.echo(f"Device: {sentence_embeddings.device} | Shape: {sentence_embeddings.shape}")

    for i, sent in enumerate(sentences):
        click.echo("\n" + click.style(f"[{i}]", fg='green') + f" {sent}")
        vec = sentence_embeddings[i]
        click.echo(f"Vector Snippet: [{vec[0]:.4f}, {vec[1]:.4f}, ...]")

if __name__ == '__main__':
    inspect_embeddings()

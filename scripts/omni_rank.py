import os
from pathlib import Path
import click
import torch
import torch.nn.functional as F
import transformers
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification
from dotenv import load_dotenv

# Suppress "Notes: UNEXPECTED / can be ignored when loading..." from model loading
transformers.logging.set_verbosity_error()

# Env Setup
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

@click.command(
    context_settings=dict(help_option_names=['-h', '--help'], max_content_width=78),
    short_help='Simulate Indexing -> Retrieval -> Reranking pipeline.',
)
@click.option(
    '-s', '--sentence',
    'sentences',
    multiple=True,
    required=True,
    help='Question (first), then one or more candidate chunks.',
)
def simulate_rag(sentences):
    """Simulate the full Indexing -> Retrieval -> Reranking pipeline.

    First -s is the question; remaining -s are candidate answer chunks.

    Example:

      omni_rank.py -s "node status?" -s "kubectl get nodes" -s "kubectl get svc"
    """ 
    if len(sentences) < 2:
        click.secho("Error: Provide at least one question and one candidate chunk.", fg='red')
        return

    query = sentences[0]
    candidates = sentences[1:]
    hf_token = os.getenv("HF_API_KEY")

    # --- MODELS (name + role) ---
    model_id = 'sentence-transformers/all-MiniLM-L6-v2'
    rerank_id = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
    click.echo(click.style("\n--- Models ---", bold=True, fg='magenta'))
    click.echo(f"  {model_id}")
    click.echo("    role: bi-encoder (indexing + query encoding)")
    click.echo(f"  {rerank_id}")
    click.echo("    role: cross-encoder (reranking)")

    # --- COMPONENT MAP ---
    click.echo(click.style("\n--- Component Lifecycle Map ---", bold=True, fg='magenta'))
    click.echo("bi_encoder:indexing         -> Converting chunks to vectors")
    click.echo("bi_encoder:query_encoding   -> Converting question to vector")
    click.echo("cosine_sim:retrieval        -> Ballpark similarity check")
    click.echo("cross_encoder:reranking     -> Deep pairwise analysis")

    # 1. BI-ENCODER STEP
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)
    model = AutoModel.from_pretrained(model_id, token=hf_token)

    inputs = tokenizer([query] + list(candidates), padding=True, truncation=True, return_tensors='pt')
    with torch.no_grad():
        out = model(**inputs)
    
    embeddings = F.normalize(mean_pooling(out, inputs['attention_mask']), p=2, dim=1)
    query_vec = embeddings[0]
    candidate_vecs = embeddings[1:]

    # 2. RETRIEVAL (Bi-Encoder Scores)
    bi_scores = torch.mm(query_vec.unsqueeze(0), candidate_vecs.T).squeeze(0)

    # 3. CROSS-ENCODER STEP
    rr_tokenizer = AutoTokenizer.from_pretrained(rerank_id, token=hf_token)
    rr_model = AutoModelForSequenceClassification.from_pretrained(rerank_id, token=hf_token)

    # Prepare pairs for cross-encoding
    pairs = [[query, cand] for cand in candidates]
    rr_inputs = rr_tokenizer(pairs, padding=True, truncation=True, return_tensors='pt')
    with torch.no_grad():
        rr_logits = rr_model(**rr_inputs).logits.squeeze(-1)

    # --- OUTPUT ---
    query_snippet = query_vec[:4].tolist()
    click.echo("\n" + click.style(f"QUESTION: {query}", bold=True, fg='cyan'))
    click.echo(f"Question Vector Snippet: {['%.4f' % x for x in query_snippet]}...")

    for i, cand in enumerate(candidates):
        bi_score = bi_scores[i].item()
        rr_score = rr_logits[i].item()
        vec_snippet = candidate_vecs[i][:4].tolist()
        
        click.echo(f"\nCHUNK [{i}]: {cand}")
        click.echo(f"Vector Snippet: {['%.4f' % x for x in vec_snippet]}...")
        click.echo(f"Bi-Encoder Score: {bi_score:.4f} (Ballpark)")
        click.echo(f"Cross-Encoder Score: {rr_score:.4f} (Precision)")

    best_idx = torch.argmax(rr_logits).item()
    click.echo("\n" + click.style(f"WINNER: Chunk [{best_idx}] is the closest match.", bold=True, bg='green', fg='white'))

if __name__ == '__main__':
    simulate_rag()

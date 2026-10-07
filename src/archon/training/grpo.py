"""Reference token-level clipped GRPO objective; no performance claims or fused kernel yet."""


def group_advantages(rewards, group_size: int, epsilon: float = 1e-6):
    if rewards.ndim != 1 or group_size < 2 or rewards.numel() % group_size:
        raise ValueError("rewards must be flat complete groups of at least two completions")
    groups = rewards.detach().float().reshape(-1, group_size)
    mean = groups.mean(dim=1, keepdim=True)
    std = groups.std(dim=1, keepdim=True, unbiased=False)
    return ((groups - mean) / (std + epsilon)).reshape(-1)


def grpo_loss(log_probs, old_log_probs, reference_log_probs, advantages, completion_mask,
              clip_epsilon: float = 0.2, beta: float = 0.01):
    import torch

    if (log_probs.ndim != 2 or log_probs.shape != old_log_probs.shape
            or log_probs.shape != reference_log_probs.shape or log_probs.shape != completion_mask.shape
            or advantages.shape != (log_probs.shape[0],)):
        raise ValueError("expected [completion,token] probabilities/mask and [completion] advantages")
    if not 0 < clip_epsilon < 1 or beta < 0:
        raise ValueError("invalid clipping or KL coefficient")
    mask = completion_mask.to(log_probs.dtype)
    lengths = mask.sum(dim=1)
    if torch.any(lengths <= 0) or torch.any((mask != 0) & (mask != 1)):
        raise ValueError("each completion requires a nonempty binary token mask")
    ratio = torch.exp(log_probs - old_log_probs.detach())
    advantage = advantages.detach().unsqueeze(1)
    unclipped = ratio * advantage
    clipped = ratio.clamp(1 - clip_epsilon, 1 + clip_epsilon) * advantage
    delta = reference_log_probs.detach() - log_probs
    kl = torch.exp(delta) - delta - 1
    token_loss = -torch.minimum(unclipped, clipped) + beta * kl
    return ((token_loss * mask).sum(dim=1) / lengths).mean()

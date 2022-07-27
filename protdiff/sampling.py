"""
Code for sampling from diffusion models
"""
import logging
from typing import *

from tqdm.auto import tqdm

import torch
from torch import nn

import utils


@torch.no_grad()
def p_sample(
    model: nn.Module,
    x: torch.Tensor,
    t: torch.Tensor,
    seq_lens: Sequence[int],
    t_index: torch.Tensor,
    betas: torch.Tensor,
    posterior_variance: torch.Tensor,
):
    # Calculate alphas and betas
    alphas = 1.0 - betas
    sqrt_recip_alphas = torch.sqrt(1.0 / alphas)
    alphas_cumprod = torch.cumprod(alphas, axis=0)
    sqrt_one_minus_alphas_cumprod = torch.sqrt(1.0 - alphas_cumprod)

    betas_t = utils.extract(betas, t, x.shape)
    sqrt_one_minus_alphas_cumprod_t = utils.extract(
        sqrt_one_minus_alphas_cumprod, t, x.shape
    )
    sqrt_recip_alphas_t = utils.extract(sqrt_recip_alphas, t, x.shape)

    # Create the attention mask
    attn_mask = torch.zeros(x.shape[:2], dtype=torch.bool, device=x.device)
    for i, l in enumerate(seq_lens):
        attn_mask[i, :l] = 1.0

    # Equation 11 in the paper
    # Use our model (noise predictor) to predict the mean
    model_mean = sqrt_recip_alphas_t * (
        x
        - betas_t
        * model(x, t, attention_mask=attn_mask)
        / sqrt_one_minus_alphas_cumprod_t
    )

    if t_index == 0:
        return model_mean
    else:
        posterior_variance_t = utils.extract(posterior_variance, t, x.shape)
        noise = torch.randn_like(x)
        # Algorithm 2 line 4:
        return model_mean + torch.sqrt(posterior_variance_t) * noise


@torch.no_grad()
def p_sample_loop(
    model: nn.Module,
    lengths: Sequence[int],
    shape: Tuple[int],
    timesteps: int,
    betas: torch.Tensor,
    posterior_variance: torch.Tensor,
    noise_modulo: Optional[Union[float, torch.Tensor]] = None,
) -> "list[torch.Tensor]":
    logging.info(f"Sampling of shape {shape} with modulo {noise_modulo}")
    device = next(model.parameters()).device

    b = shape[0]
    # start from pure noise (for each example in the batch)
    assert len(shape) == 3
    img = torch.randn(shape, device=device)
    if noise_modulo is not None:
        img = utils.broadcast_mod(img, noise_modulo)
    assert img.shape == shape, f"Mismatched shapes: {img.shape} != {shape}"

    # Report metrics on starting noise
    # amin and amax support reducing on multiple dimensions
    logging.info(
        f"Starting from noise with modulo {noise_modulo} and range {torch.amin(img, dim=(0, 1))} - {torch.amax(img, dim=(0, 1))}"
    )

    imgs = []

    for i in tqdm(
        reversed(range(0, timesteps)), desc="sampling loop time step", total=timesteps
    ):
        # Shape is (batch, seq_len, 4)
        img = p_sample(
            model=model,
            x=img,
            t=torch.full((b,), i, device=device, dtype=torch.long),  # time vector
            seq_lens=lengths,
            t_index=i,
            betas=betas,
            posterior_variance=posterior_variance,
        )

        if noise_modulo is not None:
            img = utils.broadcast_mod(img, noise_modulo)
            imgs.append(img.cpu())
        else:
            imgs.append(img.cpu())
            # img[:, :, 1:] = torch.remainder(img[:, :, 1:], 2 * torch.pi)
        imgs.append(img.cpu())
    return imgs


@torch.no_grad()
def sample(
    model: nn.Module,
    seq_lens: Sequence[int],
    seq_max_len: int,
    betas: torch.Tensor,
    posterior_variance: torch.Tensor,
    batch_size: int = 16,
    channels: int = 4,
    timesteps: int = 200,
    noise_modulo: Optional[Union[float, torch.Tensor]] = None,
) -> torch.Tensor:
    retval = p_sample_loop(
        model,
        lengths=seq_lens,
        shape=(batch_size, seq_max_len, channels),
        timesteps=timesteps,
        betas=betas,
        posterior_variance=posterior_variance,
        noise_modulo=noise_modulo,
    )[-1]

    # Trim the sequences by sequence lengths
    retval = [retval[i, :l, :] for i, l in enumerate(seq_lens)]
    return retval

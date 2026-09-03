"""Fail explicitly unless real Intel GPU compute and autograd work."""
import torch


def test_intel_gpu_compute_and_backward():
    assert torch.xpu.is_available(), "Intel GPU unavailable: verify XPU wheel and Intel driver; no CPU fallback."
    print(f"TORCH={torch.__version__}; DEVICE={torch.xpu.get_device_name(0)}", flush=True)
    x = torch.tensor([1.0, 2.0, 3.0], device="xpu", requires_grad=True)
    loss = (x * x).sum()
    loss.backward()
    torch.xpu.synchronize()
    assert x.device.type == "xpu"
    assert loss.item() == 14.0
    assert torch.equal(x.grad.cpu(), torch.tensor([2.0, 4.0, 6.0]))


def test_intel_gpu_linear_and_backward():
    assert torch.xpu.is_available(), "Intel GPU required: no CPU fallback"
    layer = torch.nn.Linear(16, 16).to("xpu")
    inputs = torch.ones(2, 16, device="xpu", requires_grad=True)
    result = layer(inputs)
    result.square().mean().backward()
    torch.xpu.synchronize()
    assert torch.isfinite(result).all().item()
    assert inputs.grad is not None and torch.isfinite(inputs.grad).all().item()

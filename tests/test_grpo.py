import pytest

from archon.training.grpo import group_advantages, grpo_loss

torch = pytest.importorskip("torch", reason="Training extra is not installed")


def test_constant_reward_group_has_no_policy_gradient():
    advantages = group_advantages(torch.tensor([1., 1., 0., 1.]), 2)
    assert torch.equal(advantages[:2], torch.zeros(2))
    assert advantages[2] < 0 < advantages[3]


def test_grpo_gradient_and_mask():
    current = torch.tensor([[-0.2, -0.3], [-0.4, -0.5]], requires_grad=True)
    old = current.detach().clone()
    reference = current.detach().clone()
    loss = grpo_loss(current, old, reference, torch.tensor([1., -1.]), torch.tensor([[1., 0.], [1., 1.]]))
    loss.backward()
    assert current.grad[0, 1] == 0
    assert current.grad[0, 0] < 0
    assert current.grad[1, 0] > 0


def test_empty_mask_is_rejected():
    probabilities = torch.zeros((2, 3))
    with pytest.raises(ValueError):
        grpo_loss(probabilities, probabilities, probabilities, torch.ones(2), torch.zeros((2, 3)))


def test_reference_objective_passes_double_precision_gradient_check():
    current = torch.tensor([[-0.4, -0.7], [-0.2, -0.5]], dtype=torch.float64, requires_grad=True)
    old = current.detach() - 0.03
    reference = current.detach() + 0.02
    advantages = torch.tensor([1., -1.], dtype=torch.float64)
    mask = torch.tensor([[1., 0.], [1., 1.]], dtype=torch.float64)
    assert torch.autograd.gradcheck(lambda value: grpo_loss(value, old, reference, advantages, mask), (current,))

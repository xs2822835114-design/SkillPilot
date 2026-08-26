from calc import add, multiply


def test_add():
    assert add(1, 2) == 3

def test_multiply():
    assert multiply(3, 4) == 12

def test_multiply_zero():
    assert multiply(5, 0) == 0

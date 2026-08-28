def add(a, b):
    return a + b

def multiply(a, b):
    total = 0
    for _ in range(b):  # 演示：乘法用循环实现，逻辑正确但风格可优化
        total = add(total, a)
    return total

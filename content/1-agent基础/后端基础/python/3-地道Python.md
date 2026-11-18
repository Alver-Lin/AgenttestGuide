# 地道 Python：让数据处理更清楚、更可组合

本篇对应蛇形图 **L3，节点 13–18**，前置为 [2-程序骨架](./2-程序骨架.md)。目标不是把代码写得最短，而是理解迭代、函数组合和协议，知道什么时候可以简化，什么时候应该保留普通循环。

示例以 **Python 3.12** 为验证环境，均使用标准库。普通 Python 代码块可独立运行；代码后的 `text` 是预期输出。继续围绕测评记录展开，最后用一个小型数据管道串起六个节点。

## 13｜推导式与迭代器

### 13.1 推导式：明确表达转换与筛选

列表推导式把“遍历、可选条件、生成元素”放在一个表达式中：

```python
scores = [85, None, 58, 92, 0]
valid = [score for score in scores if score is not None]
passed = [score for score in valid if score >= 60]
print(valid)
print(passed)
```

```text
[85, 58, 92, 0]
[85, 92]
```

写法是 `[生成的值 for 元素 in 数据 if 条件]`。不要用 `if score` 筛选缺失分数，它会把零分一起丢掉。

集合和字典也有推导式：

```python
records = [("小林", 85), ("小周", 58), ("小林", 90)]
names = {name for name, score in records}
by_name = {name: score for name, score in records}
print(sorted(names))
print(by_name["小林"])
```

```text
['小周', '小林']
90
```

字典键重复时后值覆盖前值。如果姓名可能重复，不能随意把它当作唯一标识。

两三层条件、异常处理、日志和副作用挤进推导式会降低可读性；这时用普通 `for` 更合适。也不要为了调用 `print()` 而生成一份无用列表。

### 13.2 可迭代对象与迭代器

**可迭代对象**可以通过 `iter()` 取得迭代器；**迭代器**通过 `next()` 一次提供一个值，耗尽时抛出 `StopIteration`。

```python
scores = [85, 58]
iterator = iter(scores)
print(next(iterator))
print(next(iterator))
print(next(iterator, "已结束"))
print(list(iterator))
print(list(scores))
```

```text
85
58
已结束
[]
[85, 58]
```

列表可以反复生成新的迭代器，已经耗尽的那个迭代器不会自动回到开头。`next(iterator, 默认值)` 在耗尽时返回默认值。

### 13.3 自定义迭代器协议

```python
class CountDown:
    def __init__(self, start):
        self.current = start

    def __iter__(self):
        return self

    def __next__(self):
        if self.current <= 0:
            raise StopIteration
        value = self.current
        self.current -= 1
        return value


counter = CountDown(3)
print(list(counter))
print(list(counter))
```

```text
[3, 2, 1]
[]
```

`for` 会反复取值并处理迭代结束。这里对象自身保存读取位置，因此是一次性的迭代器；它不是可以反复从头读取的容器。

**练习**：先用循环、再用推导式提取有效成绩；解释为什么第二次消费同一迭代器得到空结果。

**过关标准**：能区分容器、可迭代对象和迭代器，知道推导式何时比普通循环更清楚。

## 14｜生成器

### 14.1 yield：需要时才产出

函数体中出现 `yield`，调用后会得到生成器对象。函数体通常等到开始取值时才运行；每次产出后暂停，并保留局部状态。

```python
def passing_scores(scores):
    print("开始筛选")
    for score in scores:
        if score is not None and score >= 60:
            yield score


stream = passing_scores([85, None, 58, 92])
print("生成器已创建")
print(next(stream))
print(list(stream))
```

```text
生成器已创建
开始筛选
85
[92]
```

生成器适合逐条读文件、逐页处理结果等场景。不必先创建完整结果列表，但输入如果本来就是巨大的列表，这个列表的内存不会因此消失。

### 14.2 生成器表达式与消费边界

```python
scores = [85, 58, 92]
stream = (score for score in scores if score >= 60)
print(sum(stream))
print(list(stream))
```

```text
177
[]
```

圆括号形式生成惰性迭代结果，`sum()` 会消耗它。需要反复统计时，可以适当转成列表，或一次遍历同时累加数量与总分。

异常也可能延迟到消费时出现：生成器创建成功，不代表后面的逐条处理不会失败。

### 14.3 yield from：委托给另一段迭代

```python
def flatten(groups):
    for group in groups:
        yield from group

print(list(flatten([[85, 58], [], [92]])))
```

```text
[85, 58, 92]
```

这里相当于从每个内部列表逐个产出元素，只展开一层，不是任意嵌套数据的通用扁平化器。

### 14.4 生成器与资源生命周期

如果生成器内部打开文件，文件可能一直保持打开，直到生成器耗尽或显式关闭。提前 `break` 不代表任何生成器都会立即、可移植地释放资源。

更容易理解的做法是：在调用方的 `with` 块里消费读取结果，把资源生命周期写清楚。不要把依赖已关闭文件的生成器返回给外部后继续读取。

**练习**：写一个生成器跳过 `None`，只产出及格成绩，并用一次循环统计数量和总分。

**过关标准**：能解释惰性、耗尽与延迟异常，知道生成器不能代替资源管理。

## 15｜闭包与装饰器

### 15.1 闭包：让函数保留配置

```python
def make_checker(threshold):
    def check(score):
        return score >= threshold
    return check

normal = make_checker(60)
strict = make_checker(90)
print(normal(85), strict(85))
```

```text
True False
```

内部函数使用外层的 `threshold`，外层调用结束后，这个关联仍然存在。读取外层名字不需要 `nonlocal`；只有重新绑定它时才需要。

### 15.2 闭包的晚绑定

```python
wrong = [lambda: value for value in range(3)]
right = [lambda value=value: value for value in range(3)]
print([fn() for fn in wrong])
print([fn() for fn in right])
```

```text
[2, 2, 2]
[0, 1, 2]
```

第一组函数调用时读取同一个变量的最终值。第二组在定义时通过默认参数保存当时的值。不要把这类现象误判为“lambda 不能用于循环”。

### 15.3 装饰器：包装函数行为

```python
from functools import wraps


def announce(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"调用 {func.__name__}")
        return func(*args, **kwargs)
    return wrapper


@announce
def average(scores):
    """计算非空成绩列表的平均分。"""
    return sum(scores) / len(scores)


print(average([80, 90]))
print(average.__name__)
```

```text
调用 average
85.0
average
```

`@announce` 相当于定义后执行 `average = announce(average)`。包装器要传递参数并返回结果；忘记 `return` 会让调用方得到 `None`。

`wraps()` 保留常见元信息，并建立 `__wrapped__` 关联，便于文档和内省工具识别原函数。它不会自动验证包装器的业务逻辑。

### 15.4 带参数装饰器与边界

```python
from functools import wraps


def require_min_count(minimum):
    def decorate(func):
        @wraps(func)
        def wrapper(scores):
            if len(scores) < minimum:
                raise ValueError("成绩数量不足")
            return func(scores)
        return wrapper
    return decorate


@require_min_count(2)
def average(scores):
    return sum(scores) / len(scores)


print(average([80, 90]))
try:
    average([80])
except ValueError as exc:
    print(exc)
```

```text
85.0
成绩数量不足
```

三层分别负责接收配置、接收原函数、处理实际调用。该示例要求输入支持 `len()`，不能把任意生成器当作相同接口传入。

同步包装器不能自动变成正确的异步装饰器；需要包装异步函数时，要考虑 `async def`、`await` 以及取消传播。重试装饰器也不能对所有错误和所有写操作无限重试。

**练习**：写一个保留函数名、原返回值与原异常的调用计数装饰器。

**过关标准**：能手动展开装饰器语法，解释闭包配置与晚绑定。

## 16｜函数与迭代工具

### 16.1 partial 与缓存

```python
from functools import partial, lru_cache


def is_passed(score, threshold):
    return score >= threshold

strict = partial(is_passed, threshold=90)
print(strict(85), strict(92))

@lru_cache(maxsize=16)
def square(value):
    return value * value

print(square(4))
print(square(4))
print(square.cache_info().hits)
```

```text
False True
16
16
1
```

`partial()` 固定部分参数，得到新的可调用对象。`lru_cache()` 复用结果，参数需要可哈希；缓存会保留参数和返回值的引用。

缓存适合输入相同、结果可复用的计算，不适合不加区分地缓存当前时间、实时权限或有副作用的写操作。缓存返回可变对象时，调用方修改它也会影响后续读取；需要明确所有权和失效策略。

### 16.2 singledispatch：按首参数类型分派

```python
from functools import singledispatch


@singledispatch
def describe(value):
    return "其他类型"

@describe.register(int)
def _(value):
    return f"整数 {value}"

@describe.register(str)
def _(value):
    return f"文本 {value}"

print(describe(85))
print(describe("通过"))
```

```text
整数 85
文本 通过
```

分派基于第一个参数的运行时类型，并考虑继承关系。它不是根据所有参数类型和取值自动选择函数的通用重载机制。

### 16.3 itertools：连接、截取、累计

```python
from itertools import chain, islice, count, accumulate

print(list(chain([85], [58, 92])))
print(list(islice(count(10), 3)))
print(list(accumulate([1, 2, 3])))
```

```text
[85, 58, 92]
[10, 11, 12]
[1, 3, 6]
```

`count()` 可以无限产出，必须通过有限消费控制边界，不要直接 `list(count())`。`chain()` 按顺序连接输入，`islice()` 从迭代器截取部分结果，通常也会消耗原迭代器。

### 16.4 groupby：只合并相邻相同键

```python
from itertools import groupby
from operator import itemgetter

rows = [("A", 85), ("B", 58), ("A", 92)]
ordered = sorted(rows, key=itemgetter(0))
for group, items in groupby(ordered, key=itemgetter(0)):
    print(group, sum(score for _, score in items))
```

```text
A 177
B 58
```

`groupby()` 按连续相同的键分组，不会自动把分散的 A 合并。需要全局分组时，先排序或改用字典累计。每个分组迭代器与外部迭代共享底层输入，想保留时应及时消费或转成列表。

**练习**：按课程名称分组统计有效成绩，比较 `groupby` 与字典累计各自需要什么前提。

**过关标准**：知道这些工具的输入约束、惰性特征和缓存边界，而不只是记住名字。

## 17｜类型与数据建模

### 17.1 类型提示表达约定，不替代运行时校验

```python
def add_one(value: int) -> int:
    return value + 1

print(add_one(2))
print(add_one(2.5))
```

```text
3
3.5
```

第二次调用违反注解约定，但 Python 不会仅凭注解阻止执行。静态检查工具可以报告这种用法；读取 JSON 或用户输入时仍需校验。

常见注解包括 `list[str]`、`dict[str, float]`、`float | None`。`Optional[float]` 表示允许 `None`，不表示调用时可以省略参数；能否省略由默认值决定。

### 17.2 TypedDict 与 dataclass

```python
from typing import TypedDict
from dataclasses import dataclass


class ScoreInput(TypedDict):
    name: str
    score: float

@dataclass
class Score:
    name: str
    score: float

raw: ScoreInput = {"name": "小林", "score": 85}
record = Score(**raw)
print(type(raw).__name__)
print(record.name)
```

```text
dict
小林
```

`TypedDict` 描述字典键的静态结构，运行时仍是普通字典；`dataclass` 则创建带属性的数据对象。两者都不是自动清洗任意输入的校验框架。

### 17.3 Enum 与 NamedTuple

```python
from enum import Enum
from typing import NamedTuple


class Status(Enum):
    PENDING = "pending"
    DONE = "done"

class Result(NamedTuple):
    name: str
    score: float

result = Result("小林", 85)
print(Status.DONE.value)
print(result.name, result[1])
```

```text
done
小林 85
```

枚举适合有限状态；命名元组兼顾字段名称和元组行为。枚举对象不是它的字符串值，JSON 输出前要明确是否转换为 `.value`。

### 17.4 Protocol：表达需要哪些行为

```python
from typing import Protocol


class Scorer(Protocol):
    def score(self, text: str) -> float: ...

class LengthScorer:
    def score(self, text: str) -> float:
        return float(len(text))


def evaluate(scorer: Scorer, text: str) -> float:
    return scorer.score(text)

print(evaluate(LengthScorer(), "Python"))
```

```text
6.0
```

`LengthScorer` 没有显式继承 `Scorer`，但结构符合需要的接口。普通 Protocol 主要供静态检查使用；即使使用 `runtime_checkable`，运行时检查也不能完整验证签名和语义。

**练习**：为分数统计函数补注解，并分别设计输入字典、内部数据类和打分器协议。

**过关标准**：能区分静态约定、运行时类型和业务校验，知道何时使用枚举或协议。

## 18｜上下文管理器

### 18.1 __enter__ 与 __exit__

上下文管理器定义一段代码进入和退出时的行为，常用于资源获取与释放。

```python
class Session:
    def __enter__(self):
        print("进入")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        print("退出")
        return False

try:
    with Session():
        print("执行")
        raise ValueError("示例错误")
except ValueError:
    print("错误继续向外传播")
```

```text
进入
执行
退出
错误继续向外传播
```

`__exit__()` 返回真值会抑制块内异常。只有明确知道这个错误已处理时才这样做。若 `__enter__()` 自身失败，对应的 `__exit__()` 不会自动执行，进入阶段的部分资源需自行清理。

### 18.2 contextmanager：用生成器写管理逻辑

```python
from contextlib import contextmanager


@contextmanager
def session():
    print("获取资源")
    try:
        yield "已准备"
    finally:
        print("释放资源")

with session() as state:
    print(state)
```

```text
获取资源
已准备
释放资源
```

这类生成器应恰好 `yield` 一次。`yield` 前准备资源，之后处理退出，`finally` 确保正常异常传播过程中也会清理。

### 18.3 ExitStack 与 closing

```python
from contextlib import ExitStack

with ExitStack() as stack:
    stack.callback(print, "清理第一项")
    stack.callback(print, "清理第二项")
    print("任务执行")
```

```text
任务执行
清理第二项
清理第一项
```

`ExitStack` 适合动态数量的资源，按逆序清理。`closing(obj)` 则在退出时调用对象的 `close()`，适合提供关闭方法但没有上下文管理协议的对象。

不要把“退出时执行清理”理解成“所有副作用都能回滚”。文件已经写出的内容、已经发送的请求，都需要各自的恢复策略。

### 18.4 综合练习：逐行读取并统计成绩

下面代码使用临时文件，可以完整独立运行。文件在 `with` 块内读取，JSONL 通过生成器逐行解析，成绩只遍历一次完成统计。

```python
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


@dataclass
class Summary:
    valid: int
    passed: int
    average: float | None


def read_scores(lines):
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("记录必须是对象")
            score = row["score"]
            if score is None:
                continue
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValueError("分数必须是数值")
            if not 0 <= score <= 100:
                raise ValueError("分数超出范围")
        except (ValueError, KeyError) as exc:
            raise ValueError(f"第 {number} 行无效") from exc
        yield score


def summarize(scores, threshold=60):
    count = passed = 0
    total = 0
    for score in scores:
        count += 1
        total += score
        passed += score >= threshold
    return Summary(count, passed, total / count if count else None)


with TemporaryDirectory() as folder:
    path = Path(folder) / "scores.jsonl"
    path.write_text('\n'.join(json.dumps({"score": s}) for s in [85, None, 58, 92, 0]), encoding="utf-8")
    with path.open(encoding="utf-8") as file:
        result = summarize(read_scores(file))
    print(result)
```

```text
Summary(valid=4, passed=2, average=58.75)
```

改成空文件时应得到 `average=None`；加入非法字符串分数时应报告行号，不能把错误行悄悄算成零分。

**本层验收**：能解释管道何时执行、文件何时关闭、错误何时抛出，以及为什么没有重复消费生成器。随后进入 [4-语言内核](./4-语言内核.md)。

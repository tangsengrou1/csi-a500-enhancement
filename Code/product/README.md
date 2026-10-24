# 最终小组产品流程

本目录由最终小组代码包合并，保留独立模块与配置，不覆盖原来的 `Code/a500/`。

在仓库根目录执行：

```bash
python -m pip install -r Code/requirements-product.txt
python Code/product/run.py --check-inputs
python Code/product/run.py
```

数据布局、重训、18 个候选组合、费用及验证方法见[最终产品流程](../../docs/PRODUCT_PIPELINE.md)。完整模块导航见[代码地图](../README.md)。

运行需要本地授权数据。默认使用 `Data/product/`；可通过 `A500_PRODUCT_DATA` 指定数据根目录。仅下载源码不包含全部输入。默认输出 `Result/reproduced/`，可用 `A500_PRODUCT_OUTPUT` 指定独立输出路径。

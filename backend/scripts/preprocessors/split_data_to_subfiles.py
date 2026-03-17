import json
import random
import re
from pathlib import Path

import pandas as pd
import typer

app = typer.Typer()


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", str(name).strip())


def random_suffix() -> str:
    return f"_{random.randint(10000000, 99999999)}"


def read_table(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)
    elif suffix == ".csv":
        return pd.read_csv(file_path)
    elif suffix == ".json":
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 1 and isinstance(data[0], dict):
            return pd.DataFrame(data)
        else:
            raise ValueError("JSON 文件格式不符合要求：应为元素个数 > 1 的数组，每个元素是对象。")
    else:
        raise ValueError(f"不支持的文件格式：{suffix}")


def export_txts(df: pd.DataFrame, output_dir: Path, title_field: str = "标题"):
    output_dir.mkdir(parents=True, exist_ok=True)
    df.columns = [c.strip() for c in df.columns]

    if title_field not in df.columns:
        title_field = df.columns[0]  # fallback

    for idx, row in df.iterrows():
        title = str(row.get(title_field, "")).strip()
        if not title:
            title = f"{str(row[df.columns[0]])}{random_suffix()}"
        else:
            title = sanitize_filename(title)

        filename = f"{title}.txt"
        file_path = output_dir / filename

        # 构造内容：字段: 值，每行一个
        content = "\n".join(f"{col}: {row[col]}" for col in df.columns)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    typer.echo(f"✅ 成功导出 {len(df)} 个文件到目录：{output_dir}")


@app.command()
def convert(
    input_file: Path = typer.Argument(..., help="输入文件（.xlsx/.xls/.csv/.json）"),
    out_dir: Path = typer.Option("output", help="输出目录"),
    title_field: str = typer.Option("标题", help="标题字段名（用于文件名）"),
):
    """
    将结构化数据文件（Excel/CSV/JSON）转换为多个 .txt 文件。
    """
    try:
        df = read_table(input_file)
        export_txts(df, out_dir, title_field)
    except Exception as e:
        typer.echo(f"❌ 错误：{e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

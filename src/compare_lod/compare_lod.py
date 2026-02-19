#!/usr/bin/env python3
"""
2つの Turtle (TTL) 形式の LOD データを比較し、トリプル単位の差分を保存するツール。

- old.ttl にあって new.ttl にないトリプル → removed.ttl
- new.ttl にあって old.ttl にないトリプル → added.ttl
- さらに subject/predicate ごとに「修正前値 / 修正後値」をまとめた CSV も出力

RDF としてパースして比較するため、行順や空白の違いには影響されません。
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from rdflib import Graph, term


def load_graph(path: Path) -> Graph:
    g = Graph()
    # 拡張子からフォーマット推定（.ttl 前提だが、念のため）
    fmt = "turtle" if path.suffix.lower() in {".ttl", ".turtle"} else None
    g.parse(path, format=fmt)
    return g


def diff_graphs(old_path: Path, new_path: Path) -> Tuple[Graph, Graph, Graph, Graph]:
    """old/new の TTL を読み込み、(old_g, new_g, removed, added) を返す。"""
    print(f"Loading old: {old_path}")
    old_g = load_graph(old_path)
    print(f"  triples: {len(old_g)}")

    print(f"Loading new: {new_path}")
    new_g = load_graph(new_path)
    print(f"  triples: {len(new_g)}")

    # rdflib の Graph は集合として差集合演算が可能
    removed = old_g - new_g
    added = new_g - old_g

    print(f"Removed triples: {len(removed)}")
    print(f"Added   triples: {len(added)}")

    return old_g, new_g, removed, added


def save_graph(g: Graph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(path), format="turtle")
    print(f"Saved: {path} (triples: {len(g)})")


def build_spo_index(g: Graph) -> Dict[Tuple[term.Node, term.Node], set]:
    """Graph から (subject, predicate) → {object,...} のインデックスを作成。"""
    index: Dict[Tuple[term.Node, term.Node], set] = defaultdict(set)
    for s, p, o in g:
        index[(s, p)].add(o)
    return index


def write_diff_csv(
    old_g: Graph,
    new_g: Graph,
    csv_path: Path,
) -> None:
    """
    subject/predicate ごとに、修正前/後のオブジェクト値を CSV で出力。

    行のパターン:
      - old だけにある値: old_object に値、new_object は空
      - new だけにある値: new_object に値、old_object は空
      - old/new が 1件ずつで異なる場合: 1 行に old_object / new_object として出力
    """
    old_idx = build_spo_index(old_g)
    new_idx = build_spo_index(new_g)

    keys = set(old_idx.keys()) | set(new_idx.keys())

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["subject", "predicate", "old_object", "new_object"])

        for (s, p) in sorted(keys, key=lambda sp: (sp[0].n3(), sp[1].n3())):
            old_objs = old_idx.get((s, p), set())
            new_objs = new_idx.get((s, p), set())

            if old_objs == new_objs:
                continue

            only_old = old_objs - new_objs
            only_new = new_objs - old_objs

            # 1対1 の置き換えなら 1 行にまとめる
            if len(only_old) == 1 and len(only_new) == 1:
                old_o = next(iter(only_old))
                new_o = next(iter(only_new))
                writer.writerow([s.n3(), p.n3(), old_o.n3(), new_o.n3()])
                continue

            for o in sorted(only_old, key=lambda x: x.n3()):
                writer.writerow([s.n3(), p.n3(), o.n3(), ""])
            for o in sorted(only_new, key=lambda x: x.n3()):
                writer.writerow([s.n3(), p.n3(), "", o.n3()])

    print(f"Saved CSV diff: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="2つの TTL (LOD) を RDF として比較し、追加/削除トリプルを保存する"
    )
    parser.add_argument(
        "old_ttl",
        type=Path,
        help="旧バージョンの TTL (例: agmsearch20260111.ttl)",
    )
    parser.add_argument(
        "new_ttl",
        type=Path,
        help="新バージョンの TTL (例: agmsearch20260219.ttl)",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=Path("compare_lod_output"),
        help="差分 TTL を保存するディレクトリ (デフォルト: ./compare_lod_output)",
    )
    args = parser.parse_args()

    if not args.old_ttl.is_file():
        raise SystemExit(f"old_ttl not found: {args.old_ttl}")
    if not args.new_ttl.is_file():
        raise SystemExit(f"new_ttl not found: {args.new_ttl}")

    old_g, new_g, removed_g, added_g = diff_graphs(args.old_ttl, args.new_ttl)

    out_dir: Path = args.out_dir
    # ファイル名は元のベース名から分かりやすく生成
    old_name = args.old_ttl.stem
    new_name = args.new_ttl.stem

    removed_path = out_dir / f"{old_name}_minus_{new_name}_removed.ttl"
    added_path = out_dir / f"{new_name}_minus_{old_name}_added.ttl"
    diff_csv_path = out_dir / f"{old_name}_vs_{new_name}_diff.csv"

    save_graph(removed_g, removed_path)
    save_graph(added_g, added_path)
    write_diff_csv(old_g, new_g, diff_csv_path)

    print("Done.")


if __name__ == "__main__":
    main()


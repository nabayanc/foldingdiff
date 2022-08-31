"""
Short and easy wrapper for TMalign
"""

import os
import re
import shutil
import subprocess
import multiprocessing
import logging
from typing import List


def run_tmalign(query: str, reference: str, fast: bool = False) -> float:
    """
    Run TMalign on the two given input pdb files
    """
    assert os.path.isfile(query)
    assert os.path.isfile(reference)

    # Check if TMalign is installed
    exec = shutil.which("TMalign")
    if not exec:
        raise FileNotFoundError("TMalign not found in PATH")

    # Build the command
    cmd = f"{exec} {query} {reference}"
    if fast:
        cmd += " -fast"
    output = subprocess.check_output(cmd, shell=True)
    score_lines = []
    for line in output.decode().split("\n"):
        if line.startswith("TM-score"):
            score_lines.append(line)

    # Fetch the chain number
    key_getter = lambda s: re.findall(r"Chain_[12]{1}", s)[0]
    score_getter = lambda s: float(re.findall(r"=\s+([0-9.]+)", s)[0])
    results_dict = {key_getter(s): score_getter(s) for s in score_lines}
    return results_dict["Chain_2"]  # Normalize by reference length


def max_tm_across_refs(
    query: str, references: List[str], n_threads: int = multiprocessing.cpu_count(), fast: bool =True
) -> float:
    """
    Compare the query against each of the references in parallel and return the maximum score
    This is typically a lot of comparisons so we run with fast set to True by default
    """
    logging.info(
        f"Matching against {len(references)} references using {n_threads} workers with fast={fast}"
    )
    args = [(query, ref, fast) for ref in references]
    pool = multiprocessing.Pool(n_threads)
    values = pool.starmap(run_tmalign, args, chunksize=10)
    pool.close()
    pool.join()

    return max(values)


def main():
    """On the fly testing"""
    run_tmalign("data/7PFL.pdb", "data/7ZYA.pdb")


if __name__ == "__main__":
    main()

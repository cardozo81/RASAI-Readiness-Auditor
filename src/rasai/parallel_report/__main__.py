"""Standalone entrypoint; deliberately absent from the operational CLI."""
import argparse
from .generator import generate


def main():
    parser = argparse.ArgumentParser(description='Gerar projeção paralela offline de uma AUD selada.')
    parser.add_argument('--audit-dir', required=True)
    args = parser.parse_args()
    print(generate(args.audit_dir))


if __name__ == '__main__':
    main()

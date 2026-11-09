try:
    from scripts.evaluate import evaluate
except ImportError:
    from evaluate import evaluate

if __name__ == "__main__":
    evaluate()

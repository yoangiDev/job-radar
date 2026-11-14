import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Radar of fresh job postings from public ATS boards."""

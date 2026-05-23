from typing import Optional
 
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
 
from agent import create_agent
 
app = typer.Typer(help="PitchupAgent — natural language browser automation")
console = Console()
EXIT_COMMANDS = {"exit", "quit", "q"}
 
 
def _run_prompt(prompt: str, url: str, headless: bool) -> None:
    console.print(Panel(
        f"[bold blue]Task:[/bold blue] {prompt}\n"
        f"[bold blue]URL:[/bold blue] {url}",
        title="🤖 PitchupAgent Starting"
    ))

    agent = create_agent(headless=headless)
    result = agent.run(task=prompt, url=url)

    data = str(result.get("data", "No result"))
    if "base64" in data:
        data = data[:500] + "\n...[image data truncated]"

    status = "✅ Task Completed" if result["status"] == "success" else "❌ Task Failed"
    color = "green" if result["status"] == "success" else "red"

    # Show result data
    console.print(Panel(
        data,
        title=status,
        border_style=color
    ))

    # Show all steps taken
    console.print(Panel(data, title=status, border_style=color))
    for step in result.get("steps", []):
        console.print(f"  Step {step['step']}: {step['tool']} → {step['output'][:100]}")
 
 
def _interactive_loop(headless: bool) -> None:
    """Interactive session — ask for task + URL each time"""
    console.print(Panel(
        "Type a task and URL. Type 'exit' to quit.",
        title="🤖 PitchupAgent Interactive Mode",
        border_style="cyan",
    ))
 
    while True:
        try:
            prompt = Prompt.ask("[bold blue]task[/bold blue]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Exiting...[/dim]")
            break
 
        if not prompt:
            continue
        if prompt.lower() in EXIT_COMMANDS:
            console.print("[dim]Goodbye[/dim]")
            break
 
        url = Prompt.ask("[bold blue]url[/bold blue]", default="https://www.pitchup.com.au").strip()
 
        _run_prompt(prompt=prompt, url=url, headless=headless)
 
 
@app.command()
def run(
    prompt: Optional[str] = typer.Argument(None, help="Task to perform in plain English"),
    url: str = typer.Option("https://www.pitchup.com.au", "--url", "-u", help="Starting URL"),
    headless: bool = typer.Option(True, "--headless", help="Run browser in headless mode"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Start interactive session"),
):
    """
    Run PitchupAgent with a natural language task.
 
    Examples:
      python cli.py run "Find tennis courts in Brisbane" --url https://pitchup.com.au
      python cli.py run --interactive
    """
    if prompt is None and not interactive:
        raise typer.BadParameter("Provide a prompt or use --interactive.")
 
    if prompt:
        _run_prompt(prompt=prompt, url=url, headless=headless)
 
    if interactive:
        _interactive_loop(headless=headless)
 
 
@app.command()
def interactive(
    headless: bool = typer.Option(True, "--headless", help="Run browser in headless mode"),
):
    """Start an interactive session with PitchupAgent."""
    _interactive_loop(headless=headless)
 
 
if __name__ == "__main__":
    app()
 
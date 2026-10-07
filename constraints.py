sketch = App.ActiveDocument.getObject("Sketch")

for i, c in enumerate(sketch.Constraints, start=1):
    print(
        f"Constraint {i}: "
        f"Type={c.Type}, "
        f"First={c.First}, FirstPos={c.FirstPos}, "
        f"Second={c.Second}, SecondPos={c.SecondPos}, "
        f"Value={getattr(c, 'Value', None)}, "
        f"Name='{getattr(c, 'Name', '')}'"
    )
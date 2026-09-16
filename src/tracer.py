import sys


class ExecutionTracer:
    """Trace Python execution events."""

    def __init__(self):
        self.events = []

    def trace(self, frame, event, arg):
        function_name = frame.f_code.co_name
        line_number = frame.f_lineno

        if event == "call":
            message = f"CALL | Function {function_name}() called | Line {line_number}"

        elif event == "line":
            message = f"LINE | Line {line_number} executed | Function {function_name}()"

        elif event == "return":
            message = f"RETURN | Function {function_name}() returned | Line {line_number}"

        elif event == "exception":
            exception_type, exception_value, _ = arg
            message = (
                f"EXCEPTION | {exception_type.__name__}: "
                f"{exception_value} | Line {line_number} | "
                f"Function {function_name}()"
            )

        else:
            return self.trace

        self.events.append({
            "event": event.upper(),
            "function": function_name,
            "line": line_number,
            "message": message
        })

        print(message)

        return self.trace

    def start(self):
        """Start tracing."""
        self.events.clear()
        sys.settrace(self.trace)

    def stop(self):
        """Stop tracing."""
        sys.settrace(None)

    def get_events(self):
        """Return recorded execution events."""
        return self.events
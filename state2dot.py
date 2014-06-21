#!/usr/bin/env python

import re

def state2dot(state):
    state = "\n".join(line.strip() for line in state.split("\n"))
    state = re.sub(r'\n\^', " ^", state)
    while re.search(r"\([^ ]+ \^[^ ]+ (\|[^|]*\||[^| )]+)( \+)? \^", state):
        state = re.sub(r"\(([^ ]+) (\^[^ ]+ (\|[^|]*\||[^| )]+)( \+)?) \^", r"(\1 \2)\n(\1 ^", state)
    # at this point, everything is in (<id> ^attr val) triples... if it's not -i/--internal
    lines = set()
    count = 0
    for line in state.split("\n"):
        line = line.strip()
        if not line:
            continue
        # if the input is from -i/--internal, need to strip a few things
        # we can recognized this by checking for an internal ID
        if re.match(r"\([0-9]+:", line):
            # first, extract other stuff
            flags = re.sub(r".*(\[[0-9.]+\])(( \+)?)(( :[0-9A-Za-z-]*)*)\)$", r'\1\4', line).split()
            wma = flags[0][1:-1]
            flags = flags[1:]
            # then return the line to as if it wasn't -i/--internal
            line = re.sub(r"^\(([0-9]+): ", "(", line)
            line = re.sub(r" \[[0-9.]*\](( \+)?).*?$", r'\1)', line)
        else:
            flags = []
            wma = ""
        # all that's left is the actual (<id> ^attr val)
        ident, attr, value, accept = re.match(r"^\(([^ ]+) \^([^ ]+) (.*?)(( \+)?)\)$", line).groups()[0:4]
        if value.startswith("@"):
            lines.add('"' + value + '" [shape="doublecircle"]')
        elif not re.match("^[A-Z][0-9]+$", value):
            lines.add('"temp' + str(count) + '" [label="' + value + '", shape="box"]')
            count += 1
            value = "temp{}".format(count - 1)
        if wma:
            lines.add('"{}" -> "{}" [label="{}{}\\n[{}]"]'.format(ident, value, attr, accept, wma))
        else:
            lines.add('"{}" -> "{}" [label="{}{}"]'.format(ident, value, attr, accept))
    result = ["digraph {"]
    result.append('    node [shape="circle"];')
    result.append("    " + ";\n    ".join(lines) + ";")
    result.append("}")
    result = "\n".join(result)
    return result

if __name__ == "__main__":
    import sys
    text = ""
    if len(sys.argv) > 1:
        result = []
        for file in sys.argv[1:]:
            with open(file, "r") as fd:
                result.append(fd.read())
        text = "".join(result)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    print(state2dot(text))

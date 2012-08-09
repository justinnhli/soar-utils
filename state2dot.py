#!/usr/bin/env python

import re

def state2dot(state):
	state = "\n".join(line.strip() for line in state.split("\n"))
	state = re.sub(r'\n\^', " ^", state)
	while re.search("\([^ ]+ \^[^ ]+ (\|[^|]*\||[^| )]+)( \+)? \^", state):
		state = re.sub("\(([^ ]+) (\^[^ ]+ (\|[^|]*\||[^| )]+)( \+)?) \^", r"(\1 \2)\n(\1 ^", state)
	# at this point, everything is in (<id> ^attr val) triples... if it's not -i/--internal
	lines = set()
	count = 0
	for line in state.split("\n"):
		line = line.strip()
		if not line:
			continue
		# if the input is from -i/--internal, need to strip a few things
		# we can recognized this by checking for an internal ID
		if re.match("\([0-9]+:", line):
			# first, extract other stuff
			iid = re.sub("^\(([0-9]+):.*", r'\1', line)
			flags = re.sub(".*(\[[0-9.]+\])(( \+)?)(( :[0-9A-Za-z-]*)*)\)$", r'\1\4', line).split()
			wma = flags[0][1:-1]
			flags = flags[1:]
			# then return the line to as if it wasn't -i/--internal
			line = re.sub("^\(([0-9]+): ", "(", line)
			line = re.sub(" \[[0-9.]*\](( \+)?).*?$", r'\1)', line)
		else:
			iid = ""
			flags= []
			wma = ""
		# all that's left is the actual (<id> ^attr val)
		ident =  re.sub("^\(([^ ]+) \^([^ ]+) (.*?)(( \+)?)\)$", r'\1', line)
		attr =   re.sub("^\(([^ ]+) \^([^ ]+) (.*?)(( \+)?)\)$", r'\2', line)
		value =  re.sub("^\(([^ ]+) \^([^ ]+) (.*?)(( \+)?)\)$", r'\3', line)
		accept = re.sub("^\(([^ ]+) \^([^ ]+) (.*?)(( \+)?)\)$", r'\4', line)
		if value.startswith("@"):
			lines.add('"' + value + '" [shape="doublecircle"]')
		elif not re.match("^[A-Z][0-9]+$", value):
			lines.add('"temp' + str(count) + '" [label="' + value + '", shape="box"]')
			count += 1
			value = "temp{}".format(count - 1)
		lines.add('"{}" -> "{}" [label="{}{}\\n[{}]"]'.format(ident, value, attr, accept, wma))
	result = ["digraph {"]
	result.append('	node [shape="circle"];')
	result.append("	" + ";\n	".join(lines) + ";")
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

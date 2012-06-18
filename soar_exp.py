#!/usr/bin/env python2.7

from itertools import product
from os import environ as env, fsync
from subprocess import call, check_output, CalledProcessError, STDOUT
import re
import sys

import Python_sml_ClientInterface as sml
from state2dot import state2dot

# low level Soar functions

def create_kernel():
	kernel = sml.Kernel.CreateKernelInCurrentThread()
	if not kernel or kernel.HadError():
		print("Error creating kernel: " + kernel.GetLastErrorDescription())
		exit(1)
	return kernel

def create_agent(kernel, name):
	agent = kernel.CreateAgent("agent")
	if not agent:
		print("Error creating agent: " + kernel.GetLastErrorDescription())
		exit(1)
	return agent

# mid-level framework

def cli(agent):
	agent.RegisterForPrintEvent(sml.smlEVENT_PRINT, callback_print_message, None)
	command = raw_input("soar> ")
	while command not in ("exit", "quit"):
		if command:
			cmd = command.strip().split()[0]
			if cmd in COMMANDS:
				print(COMMANDS[cmd](command))
			else:
				print(agent.ExecuteCommandLine(command).strip())
		command = raw_input("soar> ")

def parameterize_commands(param_map, commands):
	return [cmd.format(**param_map) for cmd in commands]

def run_parameterized_commands(agent, param_map, commands):
    for cmd in parameterize_commands(param_map, commands):
		result = agent.ExecuteCommandLine(cmd)

def param_permutations(params):
	keys = sorted(params.keys())
	for values in product(*(params[key] for key in keys)):
		yield dict(zip(keys, values))

# IO

def parse_output_commands(agent, structure):
	commands = {}
	mapping = {}
	for cmd in range(0, agent.GetNumberCommands()):
		error = False
		command = agent.GetCommand(cmd)
		cmd_name = command.GetCommandName()
		if cmd_name in structure:
			parameters = {}
			for param_name in structure[cmd_name]:
				param_value = command.GetParameterValue(param_name)
				if param_value:
					parameters[param_name] = param_value
			if not error:
				commands[cmd_name] = parameters
				mapping[cmd_name] = command
		else:
			error = True
		if error:
			command.AddStatusError()
	return commands, mapping

def dot_to_input(edges):
	pass

# callback registry

def register_print_callback(kernel, agent, function, user_data=None):
	agent.RegisterForPrintEvent(sml.smlEVENT_PRINT, function, user_data)

def register_output_callback(kernel, agent, function, user_data=None):
	agent.RegisterForRunEvent(sml.smlEVENT_AFTER_OUTPUT_PHASE, function, user_data)

def register_output_change_callback(kernel, agent, function, user_data=None):
	kernel.RegisterForUpdateEvent(sml.smlEVENT_AFTER_ALL_GENERATED_OUTPUT, function, user_data)

def register_destruction_callback(kernel, agent, function, user_data=None):
	agent.RegisterForRunEvent(sml.smlEVENT_AFTER_HALTED, function, user_data)

# callback functions

def callback_print_message(mid, user_data, agent, message):
	print(message.strip())

def print_report_row(mid, user_data, agent, *args):
	condition = user_data["condition"]
	param_map = user_data["param_map"]
	domain = user_data["domain"]
	reporters = user_data["reporters"]
	if condition(param_map, domain, agent):
		pairs = []
		pairs.extend("=".join([k, str(v)]) for k, v in param_map.items())
		pairs.extend("{}={}".format(*reporter(param_map, domain, agent)) for reporter in reporters)
		print(" ".join(pairs))

def report_data_wrapper(param_map, domain, reporters, condition=None):
	if condition is None:
		condition = (lambda param_map, domain, agent: True)
	return {
			"condition": condition,
			"param_map": param_map,
			"domain": domain,
			"reporters": reporters,
			}

# common reporters

def computed_branch_name(param_map, domain, agent):
	result = re.sub(".*/", "", check_output(("ls", "-l", "{}/SoarSuite".format(env["HOME"])))[:-1]).strip()
	return ("branch", result)

def avg_decision_time(param_map, domain, agent):
	result = re.sub(".*\((.*) msec/decision.*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
	return ("avg_dc_msec", result)

def max_decision_time(param_map, domain, agent):
	result = re.sub(".*  Time \(sec\) *([0-9.]*).*", r"\1", agent.ExecuteCommandLine("stats -M"), flags=re.DOTALL)
	return ("max_dc_msec", float(result) * 1000)

def kernel_cpu_time(param_map, domain, agent):
	result = re.sub(".*Kernel CPU Time: *([0-9.]*).*", r"\1", agent.ExecuteCommandLine("stats"), flags=re.DOTALL)
	return ("kernel_cpu_msec", float(result) * 1000)

# new commands

def command_viz(command):
	command = command.strip()
	path = re.search("(--path|-p)\s+([^ ]+)", command)
	if path:
		command = re.sub("\s+(--path|-p)\s+([^ ]+)", "", command)
	if command == "viz":
		args = "--depth 1000 <s>"
	else:
		args = command[4:]
	dot = state2dot(agent.ExecuteCommandLine("print " + args))
	if path:
		path = path.group(2)
		with open(path, "w") as fd:
			fd.write(dot)
			fsync(fd)
			return "state graph writted to {}".format(path)
		return "an unknown error occured trying to write to {}".format(path)
	return dot

COMMANDS = {
		"viz":command_viz,
		}

# soar code management

def make_branch(branch):
	try:
		stdout = check_output(("make-branch", branch), stderr=STDOUT)
		return True
	except CalledProcessError as cpe:
		return False

if __name__ == "__main__":
	kernel = create_kernel()
	agent = create_agent(kernel, "agent")
	for source in sys.argv[1:]:
		print(agent.ExecuteCommandLine("source " + source))
	cli(agent)
	kernel.DestroyAgent(agent)
	kernel.Shutdown()
	del kernel

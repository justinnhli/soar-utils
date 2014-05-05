#!/usr/bin/env python3

from optparse import OptionParser
from os import chdir as cd, getcwd as pwd
from os.path import basename, dirname
import re
from sys import maxsize
from pegparse import create_parser

varIndex = 0
idNodeMap = {}
edges = set()

class Node:

    def __init__(self, nodeId):
        self.nodeId = nodeId
        self.groups = set()
        self.values = set()
        self.depth = maxsize
        self.visited = False

    def determineType(self):
        if "state" in self.groups:
            return "state"
        elif len(self.values) == 0:
            return "internal"
        elif all(re.match(r'^[+-]?[0-9]*\.?[0-9]+$', value) for value in self.values):
            return "number"
        # elif "value" not in self.groups:
        elif "attribute" in self.groups:
            return "attribute"
        else:
            return "symbol"

    def determineLabel(self):
        nodeType = self.determineType()
        if nodeType == "state":
            return self.nodeId
        elif len(self.values) == 0:
            return "<" + str(self.nodeId) + ">"
        elif nodeType == "symbol":
            return "\\n".join(self.values)
        elif nodeType == "number":
            if len(self.values) == 1:
                return self.values.pop()
            return "[" + str(min(self.values)) + " - " + str(max(self.values)) + "]"
        return "<" + self.nodeId + ">"

    def pprint(self, prefix=""):
        print(prefix + "NODE " + str(self.nodeId))
        print(prefix + "    type: " + self.determineType())
        print(prefix + "    visited: " + ("yes" if self.visited else "no"))
        print(prefix + "    depth: " + str(self.depth))
        tempList = list(self.groups)
        tempList.sort()
        print(prefix + "    groups: " + ", ".join(tempList))
        tempList = list(self.values)
        tempList.sort()
        print(prefix + "    values: " + ", ".join(tempList))

    def toDotString(self):
        attributes = set()
        attributes.add('label="%s"' % (self.determineLabel()))
        nodeType = self.determineType()
        if nodeType == "state":
            attributes.add('fillcolor="#204A87"')
            attributes.add('fontcolor="#EEEEEC"')
            attributes.add('style="filled"')
        elif nodeType == "number" or nodeType == "symbol":
            attributes.add('fontcolor="#A40000"')
        else:
            attributes.add('fontcolor="#5C3566"')
        if "stored" in self.groups:
            attributes.add('style="bold"')
        return '"%s" [%s]' % (self.nodeId, ", ".join(attributes))

class Edge:

    def __init__(self, parent, child, attr):
        self.parent = parent
        self.child = child
        self.attr = attr

    def replace(self, mapping):
        if self.parent in mapping:
            self.parent = mapping[self.parent]
        if self.child in mapping:
            self.child = mapping[self.child]
        if self.attr in mapping:
            self.attr = mapping[self.attr]

    def pprint(self, prefix=""):
        print(prefix + "(%s, %s, %s)" % (self.parent, self.child, self.attr))

    def toDotString(self, prefix=""):
        return '"%d" -> "%d"' % (self.parent, self.child)

def getNode(varid=-1):
    global varIndex, idNodeMap
    if varid >= 0 and varid in idNodeMap:
        return idNodeMap[varid]
    node = Node(varIndex)
    idNodeMap[varIndex] = node
    varIndex += 1
    return node

def replaceVarids(mapping):
    global edges
    for edge in edges:
        edge.replace(mapping)

def printInternals(prefix=""):
    global idNodeMap, edges
    for node in idNodeMap.values():
        node.pprint(prefix)
    for edge in edges:
        edge.pprint(prefix)

def compact():
    global idNodeMap, edges
    changed = True
    while changed:
        changed = False
        # delete unused nodes
        usedIds = set()
        for edge in edges:
            usedIds |= set([edge.parent, edge.child, edge.attr])
        numNodes = len(idNodeMap)
        idNodeMap = dict((key, value) for key, value in idNodeMap.items() if key in usedIds)
        if numNodes != len(idNodeMap):
            changed = True
        # delete unused edges
        numEdges = len(edges)
        edges = set(edge for edge in edges if len(set([edge.parent, edge.child, edge.attr]) & set(idNodeMap.keys())) == 3)
        if numEdges != len(edges):
            changed = True
        # delete unreachable nodes
        markReachable()
        idNodeMap = dict((key, value) for key, value in idNodeMap.items() if value.visited)

def markReachable(varids=[]):
    global idNodeMap, edges
    if len(varids) == 0:
        for varid in idNodeMap:
            getNode(varid).visited = False
        varids = set(varid for varid in idNodeMap if "state" in getNode(varid).groups)
    for varid in varids:
        getNode(varid).visited = True
    outset = set(edge for edge in findEdges(parent=(lambda n: n.nodeId in varids), child=(lambda n: not n.visited)))
    for edge in outset:
        getNode(edge.attr).visited = True
    children = set(edge.child for edge in findEdges(parent=(lambda n: n.nodeId in varids), child=(lambda n: not n.visited)))
    if len(children) > 0:
        markReachable(children)

def mergeNodes(nodeIds):
    global idNodeMap, edges
    merged = getNode()
    for nodeId in nodeIds:
        merged.groups |= idNodeMap[nodeId].groups
        merged.values |= idNodeMap[nodeId].values
        replaceVarids({nodeId: merged.nodeId})
    return merged.nodeId

def findEdges(parent=(lambda n: True), child=(lambda n: True), attr=(lambda n: True)):
    global idNodeMap, edges
    return [edge for edge in edges if parent(idNodeMap[edge.parent]) and child(idNodeMap[edge.child]) and attr(idNodeMap[edge.attr])]

def annotate():
    global idNodeMap
    # states:
    changed = True
    while changed:
        changed = False
        for node in [idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: len(n.values & set(["superstate", "topstate"])) > 0), child=(lambda n: len(n.values) == 0))]:
            if "state" not in node.groups:
                changed = True
            node.groups.add("state")
    # topstate
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: "topstate" in n.values))):
        node.groups.add("topstate")
    for node in set(idNodeMap[edge.parent] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: "superstate" in n.values), child=(lambda n: "nil" in n.values))):
        node.groups.add("topstate")
    # operators
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: "operator" in n.values))):
        node.groups.add("operator")
    # io
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: "io" in n.values))):
        node.groups.add("io")
    # {input, output, reward}-link
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "io" in n.groups), attr=(lambda n: "input-link" in n.values))):
        node.groups.add("input-link")
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "io" in n.groups), attr=(lambda n: "output-link" in n.values))):
        node.groups.add("output-link")
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: "reward-link" in n.values))):
        node.groups.add("reward-link")
    # memories
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: len(n.values & set(["smem", "epmem"])) > 0))):
        node.groups.add("memory")
    # memory commands
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "memory" in n.groups), attr=(lambda n: "command" in n.values))):
        node.groups.add("memory-cmd")
    # stored WMEs
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "memory-cmd" in n.groups), attr=(lambda n: "store" in n.values))):
        node.groups.add("stored")
    # memory command targets
    commands = set(["after", "before", "neg-query", "next", "previous", "prohibit", "query", "retrieve", "store"])
    for node in set(idNodeMap[edge.child] for edge in findEdges(parent=(lambda n: "memory-cmd" in n.groups), attr=(lambda n: len(n.values & commands) > 0))):
        node.groups.add("mem-target")

def topologicalSort(nodeIds, depth=0):
    if len(nodeIds) == 0:
        return
    for nodeId in nodeIds:
        node = idNodeMap[nodeId]
        if node.depth > depth:
            node.depth = depth
    children = set(edge.child for edge in findEdges(parent=(lambda n: n.nodeId in nodeIds), child=(lambda n: n.depth > depth)))
    topologicalSort(children, depth + 1)

def splitArchitecturals():
    global edges
    # remove state-state edges
    for edge in findEdges(attr=(lambda n: len(n.values & set(["topstate", "superstate"])) > 0)):
        edges.remove(edge)
    # split states with multiple names
    stateNameEdges = set(edge for edge in findEdges(parent=(lambda n: "state" in n.groups), attr=(lambda n: "name" in n.values), child=(lambda n: len(n.values) > 1)))
    for edge in stateNameEdges:
        edges.remove(edge)
        state = edge.parent
        attr = getNode(edge.attr)
        child = getNode(edge.child)
        names = getNode(edge.child).values
        for name in names:
            newChild = getNode()
            newChild.values.add(name)
            newChild.groups |= child.groups
            newChild.depth = child.depth
            newState = copyTree(state, {child.nodeId: newChild.nodeId})
            newAttr = getNode()
            newAttr.values |= attr.values
            newAttr.groups |= attr.groups
            newAttr.depth = attr.depth
            edges.add(Edge(newState.nodeId, newChild.nodeId, newAttr.nodeId))
        del idNodeMap[state]
        compact()
    # TODO
    # split operators with multiple names

def copyTree(varid, substitutions={}):
    global edges
    if varid in substitutions:
        return getNode(substitutions[varid])
    node = getNode(varid)
    copy = getNode()
    copy.values |= node.values
    copy.groups |= node.groups
    copy.depth = node.depth
    children = set(edge.child for edge in findEdges(parent=(lambda n: n.nodeId == varid)))
    for child in children:
        childCopy = child
        if getNode(child).depth > node.depth:
            childCopy = copyTree(child, substitutions).nodeId
        for edge in findEdges(parent=(lambda n: n.nodeId == varid), child=(lambda n: n.nodeId == child)):
            attr = getNode(edge.attr)
            attrCopy = getNode()
            attrCopy.values |= attr.values
            attrCopy.groups |= attr.groups
            attrCopy.depth = attr.depth
            edges.add(Edge(copy.nodeId, childCopy, attrCopy.nodeId))
    return copy

def mergeArchitecturals():
    global idNodeMap
    # topstate
    topstate = mergeNodes(set(varid for varid in idNodeMap if "topstate" in idNodeMap[varid].groups))
    # states
    mergeHomonamed(varid for varid in idNodeMap if "state" in idNodeMap[varid].groups)
    # operators
    mergeHomonamed(varid for varid in idNodeMap if "operator" in idNodeMap[varid].groups)
    # unnamed operator states
    for operatorId in set(edge.parent for edge in findEdges(parent=(lambda n: "operator" in n.groups))):
        operatorStates = set(edge.parent for edge in findEdges(parent=(lambda n: "state" in n.groups), child=(lambda n: n.nodeId == operatorId)))
        mergeNodes(os for os in operatorStates if len(findEdges(parent=(lambda n: n.nodeId == os), attr=(lambda n: "name" in n.values))) == 0)
    # TODO some ideas
    # if only one named state proposes an operator, merge unnamed states of that operator with the named state
    # if the name of a state/operator has multiple values, split them out into multiple states/operators
    compact()

def mergeHomonamed(varids):
    global idNodeMap
    names = {}
    for varid in varids:
        nameEdges = findEdges(parent=(lambda n: n.nodeId == varid), attr=(lambda n: len(n.values) == 1 and "name" in n.values), child=(lambda n: len(n.values) == 1))
        if len(nameEdges) == 1:
            parentId = nameEdges[0].parent
            child = idNodeMap[nameEdges[0].child]
            name = child.values.pop()
            child.values.add(name)
            if name not in names:
                names[name] = set()
            names[name].add(parentId)
    for name in names:
        recursiveMerge(mergeNodes(names[name]))

def recursiveMerge(nodeId):
    global idNodeMap
    if idNodeMap[nodeId].visited:
        return
    idNodeMap[nodeId].visited = True
    attrs = set()
    for attrNode in [idNodeMap[edge.attr] for edge in findEdges(parent=(lambda n: n.nodeId == nodeId))]:
        attrs |= attrNode.values
    if len(attrs) == 0:
        return
    mergedChildren = set()
    for attr in attrs:
        children = set(edge.child for edge in findEdges(parent=(lambda n: n.nodeId == nodeId), attr=(lambda n: attr in n.values)))
        children = set(child for child in children if shouldMerge(child))
        mergedChildren.add(mergeNodes(children))
    for child in mergedChildren:
        recursiveMerge(child)
    compact()

def shouldMerge(nodeId):
    node = idNodeMap[nodeId]
    if node.visited:
        return False
    if len(node.groups & set(["state", "operator", "mem-target"])) > 0:
        return False
    return True

class SoarViz:

    def __init__(self, options):
        with open("soar-grammar", "r") as fd:
            self.parser = create_parser(fd.read())
        self.parser.debug = options.verbose

        self.ruleFileMap = {}
        self.rules = {}

        self.errors = ""

    def soarToDot(self, files):
        self.extractRules(files)
        if self.errors:
            print(self.errors)
        """
        if len(self.rules) > 1:
            print("Blocking problem with sharing variables; only one rule accepted until solved")
            exit()
            """
        for ruleName in self.rules:
            SoarRuleGraph(ruleName, self.rules[ruleName])
        annotate()
        topologicalSort(set(varid for varid in idNodeMap if "state" in idNodeMap[varid].groups))
        splitArchitecturals()
        self.dotGraph()
        exit()
        mergeArchitecturals()

        # cheating
        #mergeNodes(set(varid for varid in idNodeMap if "state" in idNodeMap[varid].groups))
        #mergeNodes(set(varid for varid in idNodeMap if "operator" in idNodeMap[varid].groups))
        #mergeNodes(set(edge.child for edge in findEdges(parent=(lambda n: "operator" in n.groups), attr=(lambda n: "name" in n.values))))

        for node in idNodeMap.values():
            node.visited = False
        stateIds = set(varid for varid in idNodeMap if "state" in idNodeMap[varid].groups)
        for stateId in stateIds:
            recursiveMerge(stateId)
        self.dotGraph()

    def extractRules(self, files):
        dirStack = [pwd()]
        for file in set(files):
            if dirname(file):
                cd(dirname(file))
            contents = "".join(open(basename(file), "r").readlines())
            ast, position = self.parser.parse(contents, "SoarFile")
            if not ast or position != len(contents):
                self.errors += "    WARNING: only parsed " + str(position) + " of " + str(len(contents)) + " in " + pwd() + "/" + basename(file) + ": " + contents
                continue
            for soarProduction in set(ast.descendants("Code/SoarProduction")):
                productionName = soarProduction.first_descendant("ProductionName").match
                if productionName in self.ruleFileMap:
                    self.errors += "    WARNING: multiple productions named " + productionName + " exist"
                self.ruleFileMap[productionName] = file
                self.rules[productionName] = soarProduction
            dirStack.append(pwd())
            sourcedFiles = set()
            for tcl in ast.descendants("Code/Tcl/*"):
                if tcl.term == "TclPushd":
                    dirStack.append(dirStack[-1] + "/" + tcl.first_descendant("File").match)
                    cd(dirStack[-1])
                elif tcl.term == "TclPopd":
                    dirStack.pop()
                    cd(dirStack[-1])
                elif tcl.term == "TclSource":
                    fullpath = dirStack[-1] + "/" + tcl.first_descendant("File").match
                    cd(dirname(fullpath))
                    sourcedFiles.add(dirStack[-1] + "/" + tcl.first_descendant("File").match)
                    cd(dirStack[-1])
            self.extractRules(sourcedFiles)
        cd(dirStack[0])

    def dotGraph(self):
        global idNodeMap, edges
        statements = set()
        for edge in edges:
            label = ""
            statements.add('    %s' % (idNodeMap[edge.parent].toDotString()))
            statements.add('    %s' % (idNodeMap[edge.child].toDotString()))
            if len(idNodeMap[edge.attr].values) > 0:
                label = "\\n".join(idNodeMap[edge.attr].values)
            else:
                label = edge.attr
            statements.add('    %s [label="%s"]' % (edge.toDotString(), label))
        statements = list(statements)
        statements.sort()
        print("digraph soarGraph {")
        for varid in idNodeMap:
            idNodeMap[varid].pprint("    //  ")
        print("    //  EDGES (from, to, edge)")
        for edge in edges:
            edge.pprint("    //      ")
        print("\n".join(statements))
        print("}")

class SoarRuleGraph:
    # FIXME also put "value" in values.groups

    def __init__(self, productionName, ast):
        self.productionName = productionName
        self.varIdMap = {}
        self.buildGraph(ast)
        print(self.varIdMap)
        printInternals()
        self.flatten()

    def flatten(self):
        global idNodeMap, edges
        # replace variable values with the variable
        for varid in idNodeMap.keys():
            values = idNodeMap[varid].values
            if len(values) == 1:
                value = values.pop()
                if value in self.varIdMap:
                    replaceVarids({varid: self.varIdMap[value]})
                else:
                    idNodeMap[varid].values.add(value)
        # FIXME a description would be nice
        for varid in idNodeMap.keys():
            idNodeMap[varid].values = self.idValues(varid)
        usedIds = set()
        for edge in edges:
            usedIds |= set([edge.parent, edge.child, edge.attr])
        for var in self.varIdMap.keys():
            varid = self.varIdMap[var]
            if varid not in usedIds:
                # FIXME del self.varIdMap[var]
                del idNodeMap[varid]

    def idValues(self, varid):
        global idNodeMap
        values = set()
        for child in idNodeMap[varid].values:
            if child in self.varIdMap:
                childId = self.varIdMap[child]
                childValues = self.idValues(childId)
                idNodeMap[self.varIdMap[child]].values = childValues
                values |= childValues
            else:
                values.add(child)
        return values

    def buildGraph(self, ast):
        self.buildConditionGraph(ast.first_descendant("ConditionSide/FirstCondition/VariableTest"))
        for positiveCondition in ast.descendants("ConditionSide/Condition/PositiveCondition"):
            self.buildConditionGraph(positiveCondition)
        for variableAttributeValueMake in ast.descendants("ActionSide/Action/VariableAttributeValueMake"):
            self.buildActionGraph(variableAttributeValueMake)
        self.getNode(self.getVar(ast.first_descendant("ConditionSide/FirstCondition/VariableTest/Variable").match)).groups.add("state")

    def buildConditionGraph(self, ast, node=""):
        term = ast.term
        if term == "PositiveCondition":
            if ast.descendants("ConditionForMultipleIdentifiers"):
                for positiveCondition in ast.descendants("ConditionForMultipleIdentifiers/Condition/PositiveCondition"):
                    self.buildConditionGraph(positiveCondition)
            else:
                for variableTest in ast.descendants("ConditionForOneIdentifier/VariableTest"):
                    self.buildConditionGraph(variableTest)
        elif term == "VariableTest":
            var = self.getVar(ast.first_descendant("Variable").match)
            for attributeValueTest in ast.descendants("AttributeValueTest"):
                self.buildConditionGraph(attributeValueTest, var)
        elif term == "AttributeValueTest":
            curNodes = set()
            curNodes.add(node)
            for attributeTest in ast.descendants("AttributeTest"):
                nextNodes = set()
                attributes = self.possibleMatches(attributeTest.first_descendant("Test"))
                for attribute in attributes:
                    var = ""
                    if attribute.term == "Constant":
                        var = self.getVar()
                        self.getNode(var).values.add(attribute.match)
                    elif attribute.term == "Variable":
                        var = self.getVar(attribute.match)
                    self.getNode(var).groups.add("attribute")
                    nextNode = self.getVar()
                    for curNode in curNodes:
                        self.addEdge(curNode, nextNode, var)
                    nextNodes.add(nextNode)
                curNodes = nextNodes
            for valueTest in ast.descendants("ValueTest"):
                if valueTest.descendants("PreferenceTest"):
                    # HACK HACK HACK HACK
                    # FIXME the code here should call a function which returns a VARIABLE, associated with a node that contains all the values
                    # that function is the one that calls possibleMatches and then does all the hard work of merging nodes should be done in that function
                    values = self.possibleMatches(valueTest.first_descendant("PreferenceTest/Test"))
                    if valueTest.descendants("PreferenceTest/Test/ConjunctiveTest/Variable"):
                        var = self.getVar(valueTest.first_descendant("PreferenceTest/Test/ConjunctiveTest/Variable").match)
                        self.getNode(var).values |= set(value.match for value in values)
                        # FIXME this doesn't work if the values are variables
                        # the variables should be merged in that case
                        for curNode in curNodes:
                            replaceVarids({self.varIdMap[curNode]: self.varIdMap[var]})
                            self.varIdMap[curNode] = self.varIdMap[var]
                    else:
                        for value in values:
                            if value.term == "Variable":
                                value = self.getVar(value.match)
                            else:
                                value = value.match
                            for curNode in curNodes:
                                self.getNode(curNode).values.add(value)
                else:
                    structuredValueTest = valueTest.first_descendant("StructuredValueTest")
                    var = self.getVar()
                    if structuredValueTest.descendants("Variable"):
                        var = self.getVar(structuredValueTest.first_descendant("Variable").match)
                    for curNode in curNodes:
                        self.getNode(curNode).values.add(var)
                    self.buildConditionGraph(structuredValueTest.first_descendant("AttributeValueTest"), var)

    def buildActionGraph(self, ast, node=""):
        term = ast.term
        if term == "VariableAttributeValueMake":
            varNode = self.getVar(ast.first_descendant("Variable").match)
            for attributeValueMake in ast.descendants("AttributeValueMake"):
                self.buildActionGraph(attributeValueMake, varNode)
        elif term == "AttributeValueMake":
            curNode = node
            for rhsValue in ast.descendants("RhsValue"):
                var = ""
                if rhsValue.descendants("Constant"):
                    var = self.getVar()
                    self.getNode(var).values.add(rhsValue.match)
                else:
                    var = self.getVar(rhsValue.match)
                self.getNode(var).groups.add("attribute")
                nextNode = self.getVar()
                self.addEdge(curNode, nextNode, var)
                curNode = nextNode
            self.getNode(curNode).values.add(ast.first_descendant("ValueOrPreferenceList/RhsValue").match)
            self.getNode(curNode).values |= set(rhsValue.match for rhsValue in ast.descendants("ValueOrPreferenceList/ValueOrPreference/RhsValue"))

    def createTestVariable(self, test):
        # FIXME the code here should call a function which returns a VARIABLE, associated with a node that contains all the values
        # that function is the one that calls possibleMatches and then does all the hard work of merging nodes should be done in that function
        var = getVar()
        if ast.descendants("ConjunctiveTest"):
            if test.descendants("ConjunctiveTest/Variable"):
                var = self.getVar(test.first_descendant("ConjunctiveTest/Variable"))
            matches = self.possibleMatches(ast.first_descendant("ConjunctiveTest"))
            # merge all variables first
            # FIXME how to maintain these? what we want is if a particular variable has been set, then this changes too
            # that is, to be able to generate all specific combinations of when the rule would match
            variables = set(value.match for value in values if value.term == "Variable")
            varValues = set()
            for variable in variables:
                varValues &= self.getNode(variable).values
            if len(varValues) > 0:
                for variable in variables:
                    replaceVarids({self.varIdMap[variable]: self.varIdMap[var]})
                    self.varIdMap[variable] = self.varIdMap[var]
            if any(value.term == "Constant" for value in values):
                # if there are constants in the values, then all variables can only take the value of that constant
                constants = set(value.match for value in values if value.term == "Constant")
                if len(constants) == 1:
                    self.getNode(var).values = constants
        elif ast.descendants("SimpleTest/DisjunctiveTest"):
            pass
        elif ast.descendants("SimpleTest/RelationalTest"):
            ast = ast.first_descendant("SimpleTest/RelationalTest")
            matches = self.possibleMatches(ast)
        return var

    def possibleMatches(self, ast):
        term = ast.term
        if term == "ConjunctiveTest":
            paths = set()
            for simpleTest in ast.descendants("SimpleTest/*"):
                paths |= self.possibleMatches(simpleTest)
            if ast.descendants("Variable"):
                self.getNode(self.getVar(ast.first_descendant("Variable").match)).values |= set(path.match for path in paths)
            return paths
        elif term == "RelationalTest":
            if ast.descendants("Relation") and ast.first_descendant("Relation").match != "=":
                return set()
            return self.possibleMatches(ast.first_descendant("SingleTest"))
        elif term == "DisjunctiveTest":
            return set(ast.descendants("Constant"))
        elif term == "SingleTest":
            return set(ast.descendants(""))

    def addEdge(self, parent, child, attr):
        global edges
        edges.add(Edge(self.varIdMap[parent], self.varIdMap[child], self.varIdMap[attr]))

    def getNode(self, var):
        global idNodeMap
        if var not in self.varIdMap:
            var = self.getVar(var)
        return idNodeMap[self.varIdMap[var]]

    def getVar(self, var=""):
        global idNodeMap
        if var in self.varIdMap:
            return var
        node = getNode()
        if not re.match("^<.*>$", var):
            var = "<" + var + ("-" if var else "") + str(node.nodeId) + ">"
        self.varIdMap[var] = node.nodeId
        node.groups.add(self.productionName)
        return var

# MAIN

def main():
    optParser = OptionParser(usage="usage: %prog [options] FILE ...")
    optParser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False, help="show what the parser is doing")
    (options, args) = optParser.parse_args()

    soarviz = SoarViz(options)

    soarviz.soarToDot(args)

if __name__ == "__main__":
    main()

import os

from pypy.rlib.parsing.parsing import ParseError

from rupypy import ast
from rupypy.lexer import Lexer
from rupypy.utils import make_parse_function


with open(os.path.join(os.path.dirname(__file__), "grammar.txt")) as f:
    grammar = f.read()

_parse, ToASTVisitor = make_parse_function(grammar, Lexer)


class Transformer(object):
    def error(self, node):
        raise ParseError(node.getsourcepos(), None)

    def visit_main(self, node):
        return ast.Main(self.visit_block(node))

    def visit_block(self, node, start_idx=0, end_idx=-1):
        if end_idx == -1:
            end_idx = len(node.children)
        stmts = []

        assert end_idx >= 0
        for node in node.children[start_idx:end_idx]:
            if node.symbol == "line":
                if not node.children:
                    continue
                node = node.children[0]
            stmts.append(self.visit_stmt(node))
        return ast.Block(stmts)

    def visit_stmt(self, node):
        if len(node.children) == 2:
            return ast.Return(self.visit_expr(node.children[1]))
        return ast.Statement(self.visit_expr(node.children[0]))

    def visit_send_block(self, node):
        send = self.visit_real_send(node.children[0])
        assert isinstance(send, ast.Send)
        block_args = []
        start_idx = 2
        if node.children[2].symbol == "arglist":
            block_args, _ = self.visit_arglist(node.children[2])
            start_idx += 1
        block = self.visit_block(node, start_idx=start_idx, end_idx=len(node.children) - 1)
        return ast.SendBlock(
            send.receiver,
            send.method,
            send.args,
            block_args,
            block,
            node.getsourcepos().lineno
        )

    def visit_expr(self, node):
        if node.children[0].symbol == "assignment":
            return self.visit_assignment(node.children[0])
        elif node.children[0].symbol == "yield":
            return self.visit_yield(node.children[0])
        return self.visit_arg(node.children[0])

    def visit_assignment(self, node):
        target = self.visit_arg(node.children[0])
        oper = node.children[1].additional_info
        value = self.visit_expr(node.children[2])
        return target.convert_to_assignment(self, node.children[0], oper, value)

    def visit_yield(self, node):
        args = []
        if len(node.children) == 2:
            args = self.visit_send_args(node.children[1])
        return ast.Yield(args, node.children[0].getsourcepos().lineno)

    def visit_arg(self, node):
        if node.symbol == "arg":
            node = node.children[0]

        symname = node.symbol
        if symname in ["comparison", "shiftive", "additive", "multitive"]:
            return self.visit_subexpr(node)
        elif symname == "range":
            return self.visit_range(node)
        elif symname == "unary_op":
            return self.visit_unaryop(node)
        elif symname == "splat":
            return ast.Splat(self.visit_arg(node.children[0]))
        elif symname == "send":
            return self.visit_send(node)
        elif symname == "primary":
            return self.visit_primary(node)
        elif symname == "do_block":
            return self.visit_send_block(node)
        raise NotImplementedError(symname)

    def visit_subexpr(self, node):
        return ast.BinOp(
            node.children[1].additional_info,
            self.visit_arg(node.children[0]),
            self.visit_arg(node.children[2]),
            node.getsourcepos().lineno,
        )

    def visit_unaryop(self, node):
        return ast.UnaryOp(
            node.children[0].additional_info,
            self.visit_arg(node.children[1]),
            node.getsourcepos().lineno
        )

    def visit_range(self, node):
        inclusive = node.children[1].additional_info == "..."
        return ast.Range(
            self.visit_arg(node.children[0]),
            self.visit_arg(node.children[2]),
            inclusive=inclusive,
        )

    def visit_send(self, node):
        if node.children[0].symbol == "real_send":
            return self.visit_real_send(node.children[0])
        raise NotImplementedError

    def visit_real_send(self, node):
        if node.children[0].symbol != "primary":
            if node.children[0].symbol == "global_block":
                node = node.children[0]
                block_args, block = self.visit_braces_block(node.children[1])
                return ast.SendBlock(
                    ast.Self(node.getsourcepos().lineno),
                    node.children[0].additional_info,
                    [],
                    block_args,
                    block,
                    node.getsourcepos().lineno
                )
            target = ast.Self(node.getsourcepos().lineno)
            name = node.children[0].additional_info
            args = self.visit_send_args(node.children[1].children[0])
            if len(node.children) == 3:
                block_args, block = self.visit_braces_block(node.children[2])
                return ast.SendBlock(
                    target, name, args, block_args, block, node.getsourcepos().lineno
                )
            else:
                return ast.Send(target, name, args, node.getsourcepos().lineno)

        target = self.visit_primary(node.children[0])
        for trailer in node.children[1].children:
            node = trailer.children[0]
            if node.symbol in ["attribute", "subscript"]:
                if node.symbol == "attribute":
                    method = node.children[0].children[0].additional_info
                    if len(node.children) == 1:
                        args = []
                    elif node.children[1].symbol == "block":
                        block_args, block = self.visit_braces_block(node.children[1])
                        target = ast.SendBlock(
                            target, method, [], block_args, block, node.getsourcepos().lineno
                        )
                        continue
                    else:
                        args = self.visit_send_args(node.children[1].children[0])
                elif node.symbol == "subscript":
                    args = [self.visit_arg(node.children[0])]
                    method = "[]"
                else:
                    assert False
                if len(node.children) == 3:
                    block_args, block = self.visit_braces_block(node.children[2])
                    target = ast.SendBlock(
                        target, method, args, block_args, block, node.getsourcepos().lineno
                    )
                else:
                    target = ast.Send(
                        target,
                        method,
                        args,
                        node.getsourcepos().lineno
                    )
            elif node.symbol == "constant":
                target = ast.LookupConstant(target, node.children[1].additional_info, node.getsourcepos().lineno)
            else:
                raise NotImplementedError
        return target

    def visit_send_args(self, node):
        return [self.visit_arg(n) for n in node.children]

    def visit_braces_block(self, node):
        block_args = []
        start_idx = 0
        if node.children[start_idx].symbol == "arglist":
            block_args, _ = self.visit_arglist(node.children[start_idx])
            start_idx += 1
        block = self.visit_block(node, start_idx=start_idx, end_idx=len(node.children))
        return block_args, block

    def visit_primary(self, node):
        if node.children[0].symbol == "literal":
            return self.visit_literal(node.children[0])
        elif node.children[0].symbol == "varname":
            return self.visit_varname(node.children[0])
        elif node.children[0].additional_info == "(":
            return self.visit_expr(node.children[1])
        elif node.children[0].additional_info == "[":
            return self.visit_array(node)
        elif node.children[0].additional_info == "if":
            return self.visit_if(node)
        elif node.children[0].additional_info == "unless":
            return self.visit_unless(node)
        elif node.children[0].additional_info == "while":
            return self.visit_while(node)
        elif node.children[0].additional_info == "def":
            return self.visit_def(node)
        elif node.children[0].additional_info == "class":
            return self.visit_class(node)
        elif node.children[0].additional_info == "module":
            return self.visit_module(node)
        elif node.children[0].additional_info == "begin":
            return self.visit_begin(node)
        raise NotImplementedError(node.symbol)

    def visit_array(self, node):
        if len(node.children) == 3:
            items = [
                self.visit_arg(n) for n in node.children[1].children
            ]
        else:
            items = []
        return ast.Array(items)

    def visit_literal(self, node):
        symname = node.children[0].symbol
        if symname == "NUMBER":
            return self.visit_number(node.children[0])
        elif symname == "symbol":
            return self.visit_symbol(node.children[0])
        elif symname == "STRING":
            return self.visit_string(node.children[0])
        raise NotImplementedError(symname)

    def visit_varname(self, node):
        if node.children[0].symbol == "AT_SIGN":
            return ast.InstanceVariable(node.children[1].additional_info)
        elif node.children[0].symbol == "DOLLAR":
            return ast.Global("$" + node.children[1].additional_info)
        elif node.children[0].additional_info[0].isupper():
            return ast.LookupConstant(ast.Scope(node.getsourcepos().lineno), node.children[0].additional_info, node.getsourcepos().lineno)
        else:
            return ast.Variable(node.children[0].additional_info, node.getsourcepos().lineno)

    def visit_if(self, node):
        if_node = node.children[1]
        if_cond = self.visit_expr(if_node.children[0])
        if_block = self.visit_block(if_node, start_idx=2, end_idx=len(if_node.children))
        if len(node.children) == 3:
            else_node = node.children[2]
            else_block = self.visit_block(else_node, start_idx=1, end_idx=len(else_node.children))
        else:
            else_block = ast.Block([])
        return ast.If(if_cond, if_block, else_block)

    def visit_unless(self, node):
        return ast.If(
            self.visit_expr(node.children[1]),
            ast.Block([]),
            self.visit_block(node, start_idx=3, end_idx=len(node.children) - 1),
        )

    def visit_while(self, node):
        return ast.While(
            self.visit_expr(node.children[1]),
            self.visit_block(node, start_idx=3, end_idx=len(node.children) - 1),
        )

    def visit_def(self, node):
        name_node = node.children[1]
        if len(name_node.children) == 1:
            parent = None
            name = name_node.children[0].additional_info
        else:
            parent = self.visit_varname(name_node.children[0])
            name = name_node.children[1].additional_info
        args, block_arg = self.visit_argdecl(node.children[2])
        return ast.Function(
            parent,
            name,
            args,
            block_arg,
            self.visit_block(node, start_idx=3, end_idx=len(node.children) - 1),
        )

    def visit_class(self, node):
        superclass = None
        block_start_idx = 2
        if node.children[2].symbol == "LT":
            superclass = self.visit_varname(node.children[3])
            block_start_idx += 2
        return ast.Class(
            node.children[1].additional_info,
            superclass,
            self.visit_block(node, start_idx=block_start_idx, end_idx=len(node.children) - 1),
        )

    def visit_module(self, node):
        return ast.Module(
            node.children[1].additional_info,
            self.visit_block(node, start_idx=2, end_idx=len(node.children) - 1)
        )

    def visit_begin(self, node):
        idx = 0
        while idx < len(node.children):
            if node.children[idx].symbol in ["rescue", "ensure"]:
                break
            idx += 1
        body_block = self.visit_block(node, start_idx=1, end_idx=idx)
        handlers = []
        while node.children[idx].symbol == "rescue":
            handlers.append(self.visit_rescue(node.children[idx]))
            idx += 1
        if handlers:
            body_block = ast.TryExcept(body_block, handlers)
        if node.children[idx].symbol == "ensure":
            ensure_node = node.children[idx]
            block = self.visit_block(ensure_node, start_idx=1, end_idx=len(ensure_node.children))
            body_block = ast.TryFinally(body_block, block)
        return body_block

    def visit_rescue(self, node):
        exception = None
        idx = 1
        if node.children[1].symbol == "varname":
            exception = self.visit_varname(node.children[1])
            idx += 1
        name = None
        if node.children[idx].symbol == "ARROW":
            name = node.children[idx + 1].additional_info
            idx += 2
        block = self.visit_block(node, start_idx=idx, end_idx=len(node.children))
        return ast.ExceptHandler(exception, name, block)

    def visit_argdecl(self, node):
        if not node.children:
            return [], None
        return self.visit_arglist(node.children[0])

    def visit_arglist(self, node):
        # 0 indicates no defaults have been seen, 1 indicates a section of
        # defaults has been started (but not finished), and 2 indicates that
        # there have been defaults and then normal args after it, at this point
        # seeing another default argument is an error
        default_seen = 0
        block_arg = None
        args = []
        for n in node.children:
            if block_arg:
                self.error(n)
            if len(n.children) == 2 and n.children[0].symbol == "AMP":
                block_arg = n.children[1].additional_info
            elif len(n.children) == 2:
                name = n.children[0].additional_info
                if default_seen == 2:
                    self.error(n)
                default_seen = 1
                args.append(ast.Argument(name, self.visit_arg(n.children[1])))
            else:
                name = n.children[0].additional_info
                if default_seen == 1:
                    default_seen = 2
                args.append(ast.Argument(name))
        return args, block_arg

    def visit_number(self, node):
        if "." in node.additional_info:
            return ast.ConstantFloat(float(node.additional_info))
        else:
            return ast.ConstantInt(int(node.additional_info))

    def visit_symbol(self, node):
        return ast.ConstantSymbol(node.children[0].additional_info)

    def visit_string(self, node):
        return ast.ConstantString(node.additional_info)

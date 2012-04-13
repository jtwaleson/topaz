from rupypy.module import ClassDef
from rupypy.objects.objectobject import W_BaseObject


class W_IntObject(W_BaseObject):
    _immutable_fields_ = ["intvalue"]

    classdef = ClassDef("Fixnum", W_BaseObject.classdef)

    def __init__(self, intvalue):
        self.intvalue = intvalue

    def int_w(self, space):
        return self.intvalue

    @classdef.method("to_s")
    def method_to_s(self, space):
        return space.newstr_fromstr(str(self.intvalue))

    @classdef.method("+", other=int)
    def method_add(self, space, other):
        return space.newint(self.intvalue + other)

    @classdef.method("-", other=int)
    def method_sub(self, space, other):
        return space.newint(self.intvalue - other)

    @classdef.method("*", other=int)
    def method_mul(self, space, other):
        return space.newint(self.intvalue * other)

    @classdef.method("==", other=int)
    def method_eq(self, space, other):
        return space.newbool(self.intvalue == other)

    @classdef.method("!=", other=int)
    def method_ne(self, space, other):
        return space.newbool(self.intvalue != other)

    @classdef.method("<", other=int)
    def method_lt(self, space, other):
        return space.newbool(self.intvalue < other)

    @classdef.method(">", other=int)
    def method_gt(self, space, other):
        return space.newbool(self.intvalue > other)
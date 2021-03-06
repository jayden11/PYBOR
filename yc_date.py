# Copyright © 2017 Ondrej Martinsky, All rights reserved
# http://github.com/omartinsky/pybor
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


from yc_helpers import *

from dateutil.relativedelta import relativedelta
from numpy import *
import dateutil.parser
import enum, calendar, datetime

class Tenor:
    def __init__(self, s):
        try:
            assert isinstance(s, str)
            self.string = s
            self.n = s[:-1]
            self.n = int(self.n) if self.n != "" else 0
            self.unit = s[-1:]
            assert self.unit in ['F', 'D', 'M', 'Q', 'Y']
        except BaseException as ex:
            raise BaseException("Unable to parse tenor %s" % s) from ex

    def __eq__(self, other):
        return self.string == other.string

    def __neg__(self):
        return Tenor("-%s" % self.string) if self.string[0]!="-" else Tenor(self.string[1:])

    def __str__(self):
        return self.string

class RollType(enum.Enum):
    NONE=0
    FOLLOWING=1
    PRECEDING=2
    MODIFIED_FOLLOWING=3
    MODIFIED_PRECEDING=4

class StubType(enum.Enum):
    NOT_ALLOWED=0
    FRONT_STUB_SHORT=1
    FRONT_STUB_LONG=2
    BACK_STUB_SHORT=3
    BACK_STUB_LONG=4

excelBaseDate = datetime.date(1899, 12, 30)

def pydate_to_exceldate(d):
    xldate = int((d - excelBaseDate).days)
    assert xldate >= 61, "Do not allow dates below 1 March 1900, Excel incorrectly assumes 1900 is a leap year"
    return xldate

def exceldate_to_pydate(d):
    assert isinstance(d, int)
    assert d >= 61, "Do not allow dates below 1 March 1900, Excel incorrectly assumes 1900 is a leap year"
    return excelBaseDate + relativedelta(days=d)

def date_step(date, tenor, preserve_eom=False):
    assert isinstance(date, int)
    assert isinstance(tenor, Tenor)
    assert tenor.unit != 'E'
    pydate = exceldate_to_pydate(date)
    pydate2 = pydate + create_relativedelta(tenor.n, tenor.unit)
    if preserve_eom:
        lastDay = calendar.monthrange(pydate.year, pydate.month)[1]
        if pydate.day == lastDay:
            d2 = calendar.monthrange(pydate2.year, pydate2.month)[1]
            pydate2 = datetime.date(pydate2.year, pydate2.month, d2)
    date2 = pydate_to_exceldate(pydate2)
    return date2

def date_roll(date, roll_type, calendar):
    assert isinstance(date, int)
    assert isinstance(roll_type, RollType)
    if roll_type==RollType.FOLLOWING:
        while calendar.is_holiday(date): date+=1
        return date
    elif roll_type == RollType.PRECEDING:
        while calendar.is_holiday(date): date -= 1
        return date
    else:
        raise BaseException("Roll type %s not implemented", roll_type)

def calculate_spot_date(trade_date, spot_offset, calendar):
    assert not calendar.is_holiday(trade_date)
    spot_date = trade_date
    tenor1D = Tenor('1D')
    for i in range(spot_offset):
        spot_date = date_step(spot_date, tenor1D, preserve_eom=False)
        spot_date = date_roll(spot_date, RollType.FOLLOWING, calendar)
    assert not calendar.is_holiday(spot_date)
    return spot_date

def create_date(arg, reference_date=None): # Creates excel date
    if isinstance(arg, int):
        return arg
    elif isinstance(arg, datetime.date):
        return pydate_to_exceldate(arg)
    elif isinstance(arg, str) and arg[0:4].isdigit():
        return pydate_to_exceldate(dateutil.parser.parse(arg).date())
    elif isinstance(arg, str):
        assert reference_date is not None
        ret = reference_date
        tenors = arg.split("+")
        for t in tenors:
            if t == 'E': continue
            ret = date_step(ret, Tenor(t))
        return ret
    elif isinstance(arg, Tenor):
        if arg.unit == 'E':
            return create_date(reference_date)
        return date_step(reference_date, arg)
    assert False, (type(arg), arg)


def calculate_dcfs(dates, dcc):
    numerator = dates[1:] - dates[:-1]
    return numerator / dcc.get_denominator()


def calculate_dcf(date0, date1, dcc):
    numerator = date1 - date0
    return numerator / dcc.get_denominator()


def create_relativedelta(n, unit):
    if unit == 'M':
        return relativedelta(months=n)
    elif unit == 'D':
        return relativedelta(days=n)
    elif unit == 'Y':
        return relativedelta(years=n)
    elif unit == 'Q':
        return relativedelta(months=3 * n)
    elif unit == 'F':
        return relativedelta(months=3 * n)  # todo
    else:
        raise BaseException("Unknown unit %s" % unit)

def generate_schedule(start, end, step, stub_type=StubType.FRONT_STUB_SHORT):
    assert isinstance(start, int)
    assert isinstance(end, int)
    assert isinstance(step, Tenor)
    assert isinstance(stub_type, StubType)
    if stub_type==StubType.NOT_ALLOWED:
        d = start
        out = []
        while d <= end:
            out.append(d)
            d = date_step(d, step)
        mismatch = out[-1] - end
        if mismatch!=0:
            raise BaseException("Function generate_schedule for start=%s, end=%s, step=%s results in unallowed stub (mismatch %i days)" %
                                (fromexceldate(start), fromexceldate(end), step.string, mismatch))
        return array(out)
    if stub_type==StubType.BACK_STUB_SHORT:
        d = start
        out = []
        while d < end:
            out.append(d)
            d = date_step(d, step)
        if out[-1]!=end:
            out.append(end)
        return array(out)
    elif stub_type == StubType.BACK_STUB_LONG:
        d = start
        out = []
        while date_step(d, step) <= end:
            out.append(d)
            d = date_step(d, step)
        if out[-1]!=end:
            out.append(end)
        return array(out)
    elif stub_type == StubType.FRONT_STUB_SHORT:
        d = end
        out = []
        stepinv = -step
        while d > start:
            out.append(d)
            d = date_step(d, stepinv)
        if out[-1]!=start:
            out.append(start)
        return array(out[::-1])
    elif stub_type == StubType.FRONT_STUB_LONG:
        d = end
        out = []
        stepinv = -step
        while date_step(d, stepinv) >= start:
            out.append(d)
            d = date_step(d, stepinv)
        if out[-1]!=start:
            out.append(start)
        return array(out[::-1])
    else:
        raise BaseException("Other stub types not supported")

# endregion

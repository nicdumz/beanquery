__copyright__ = "Copyright (C) 2014-2017  Martin Blais"
__license__ = "GNU GPLv2"

import datetime
import decimal
import io
import unittest
import textwrap

from decimal import Decimal

from beancount.core.number import D
from beancount.core import inventory
from beancount.core.inventory import from_string as I
from beancount.parser import cmptest
from beancount.utils import misc_utils
from beancount import loader

from beanquery import query_parser as qp
from beanquery import query_compile as qc
from beanquery import query_env as qe
from beanquery import query_execute as qx

# pylint: disable=unused-import
from beanquery import compat


class QueryBase(cmptest.TestCase):

    maxDiff = 8192

    # Default execution contexts.
    xcontext_entries = qe.FilterEntriesEnvironment()
    xcontext_targets = qe.TargetsEnvironment()
    xcontext_postings = qe.FilterPostingsEnvironment()

    def setUp(self):
        super().setUp()
        self.parser = qp.Parser()

    def parse(self, bql_string):
        """Parse a query.

        Args:
          bql_string: An SQL query to be parsed.
        Returns:
          A parsed statement (Select() node).
        """
        return self.parser.parse(bql_string.strip())

    def compile(self, bql_string):
        """Parse a query and compile it.

        Args:
          bql_string: An SQL query to be parsed.
        Returns:
          A compiled EvalQuery node.
        """
        return qc.compile_select(self.parse(bql_string),
                                 self.xcontext_targets,
                                 self.xcontext_postings,
                                 self.xcontext_entries)

    def check_query(self,
                    input_string, bql_string,
                    expected_types, expected_rows,
                    sort_rows=False,
                    debug=False):

        entries, _, options_map = loader.load_string(input_string)
        query = self.compile(bql_string)
        result_types, result_rows = qx.execute_query(query, entries, options_map)

        if debug:
            with misc_utils.box('result_types'):
                print(result_types)
            with misc_utils.box('result_rows'):
                print(result_rows)
        self.assertEqual(expected_types, result_types)
        if sort_rows:
            result_rows.sort()
        self.assertEqual(expected_rows, result_rows)

    def check_sorted_query(self,
                           input_string, bql_string,
                           expected_types, expected_rows):
        return self.check_query(input_string, bql_string,
                                expected_types, expected_rows, True)


class CommonInputBase(unittest.TestCase):
    INPUT = textwrap.dedent("""

    2010-01-01 open Assets:Bank:Checking
    2010-01-01 open Assets:ForeignBank:Checking
    2010-01-01 open Assets:Bank:Savings

    2010-01-01 open Expenses:Restaurant

    2010-01-01 * "Dinner with Cero"
      Assets:Bank:Checking       100.00 USD
      Expenses:Restaurant       -100.00 USD

    2011-01-01 * "Dinner with Uno"
      Assets:Bank:Checking       101.00 USD
      Expenses:Restaurant       -101.00 USD

    2012-02-02 * "Dinner with Dos"
      Assets:Bank:Checking       102.00 USD
      Expenses:Restaurant       -102.00 USD

    2013-03-03 * "Dinner with Tres"
      Assets:Bank:Checking       103.00 USD
      Expenses:Restaurant       -103.00 USD

    2013-10-10 * "International Transfer"
      Assets:Bank:Checking         -50.00 USD
      Assets:ForeignBank:Checking  -60.00 CAD @ 1.20 USD

    2014-04-04 * "Dinner with Quatro"
      Assets:Bank:Checking       104.00 USD
      Expenses:Restaurant       -104.00 USD

    """)
    def setUp(self):
        super().setUp()
        self.entries, _, self.options_map = loader.load_string(textwrap.dedent(self.INPUT))
        self.context = qx.create_row_context(self.entries, self.options_map)


class TestFundamentals(QueryBase):

    def setUp(self):
        super().setUp()
        self.entries, errors, self.options = loader.load_string("""
          2022-04-05 commodity TEST
            rate: 42
          2022-04-05 open Assets:Tests
          2022-04-05 * "Test"
            Assets:Tests  1.000 TEST
              int: 1
              decimal: 1.2
              bool: TRUE
              str: "str"
              str3: "3"
              str4: "4.0"
              date: 2022-04-05
              null: NULL
        """, dedent=True)

    def assertResult(self, query, result, dtype=None):
        dtypes, rows = qx.execute_query(self.compile(query), self.entries, self.options)
        self.assertEqual([dtype for name, dtype in dtypes], [dtype or type(result)])
        self.assertEqual(rows, [(result, )])

    def assertError(self, query):
        with self.assertRaises(qc.CompilationError):
            dtypes, rows = qx.execute_query(self.compile(query), self.entries, self.options)

    def test_type_casting(self):
        # bool
        self.assertResult("SELECT bool(TRUE)", True)
        self.assertResult("SELECT bool(1)", True)
        self.assertResult("SELECT bool(1.1)", True)
        self.assertResult("SELECT bool('foo')", True)
        self.assertResult("SELECT bool(NULL)", None, bool)
        self.assertResult("SELECT bool(2022-04-05)", True)
        self.assertResult("SELECT bool(meta('int'))", True)
        self.assertResult("SELECT bool(meta('decimal'))", True)
        self.assertResult("SELECT bool(meta('bool'))", True)
        self.assertResult("SELECT bool(meta('str'))", True)
        self.assertResult("SELECT bool(meta('date'))", True)
        self.assertResult("SELECT bool(meta('null'))", None, bool)
        self.assertResult("SELECT bool(meta('missing'))", None, bool)

        # int
        self.assertResult("SELECT int(TRUE)", 1)
        self.assertResult("SELECT int(1)", 1)
        self.assertResult("SELECT int(1.2)", 1)
        self.assertResult("SELECT int('1')", 1)
        self.assertResult("SELECT int('foo')", None, int)
        self.assertError ("SELECT int(NULL)")
        self.assertError ("SELECT int(2022-04-05)")
        self.assertResult("SELECT int(meta('int'))", 1)
        self.assertResult("SELECT int(meta('decimal'))", 1)
        self.assertResult("SELECT int(meta('bool'))", 1)
        self.assertResult("SELECT int(meta('str'))", None, int)
        self.assertResult("SELECT int(meta('str3'))", 3)
        self.assertResult("SELECT int(meta('str4'))", None, int)
        self.assertResult("SELECT int(meta('date'))", None, int)
        self.assertResult("SELECT int(meta('null'))", None, int)
        self.assertResult("SELECT int(meta('missing'))", None, int)

        # decimal
        self.assertResult("SELECT decimal(TRUE)", Decimal(1))
        self.assertResult("SELECT decimal(1)", Decimal(1))
        self.assertResult("SELECT decimal(1.2)", Decimal('1.2'))
        self.assertResult("SELECT decimal('1.2')", Decimal('1.2'))
        self.assertResult("SELECT decimal('foo')", None, Decimal)
        self.assertError ("SELECT decimal(NULL)")
        self.assertError ("SELECT decimal(2022-04-05)")
        self.assertResult("SELECT decimal(meta('int'))", Decimal(1))
        self.assertResult("SELECT decimal(meta('decimal'))", Decimal('1.2'))
        self.assertResult("SELECT decimal(meta('bool'))", Decimal(1))
        self.assertResult("SELECT decimal(meta('str'))", None, Decimal)
        self.assertResult("SELECT decimal(meta('str3'))", Decimal(3))
        self.assertResult("SELECT decimal(meta('str4'))", Decimal('4.0'))
        self.assertResult("SELECT decimal(meta('date'))", None, Decimal)
        self.assertResult("SELECT decimal(meta('null'))", None, Decimal)
        self.assertResult("SELECT decimal(meta('missing'))", None, Decimal)

        # str
        self.assertResult("SELECT str(TRUE)", 'TRUE')
        self.assertResult("SELECT str(1)", '1')
        self.assertResult("SELECT str(1.1)", '1.1')
        self.assertResult("SELECT str('foo')", 'foo')
        self.assertResult("SELECT str(NULL)", None, str)
        self.assertResult("SELECT str(2022-04-05)", '2022-04-05')
        self.assertResult("SELECT str(meta('int'))", '1')
        self.assertResult("SELECT str(meta('decimal'))", '1.2')
        self.assertResult("SELECT str(meta('bool'))", 'TRUE')
        self.assertResult("SELECT str(meta('str'))", 'str')
        self.assertResult("SELECT str(meta('date'))", '2022-04-05')
        self.assertResult("SELECT str(meta('null'))", None, str)
        self.assertResult("SELECT str(meta('missing'))", None, str)

        # date
        self.assertError ("SELECT date(TRUE)")
        self.assertError ("SELECT date(1)")
        self.assertError ("SELECT date(1.2)")
        self.assertResult("SELECT date('1.2')", None, datetime.date)
        self.assertResult("SELECT date('foo')", None, datetime.date)
        self.assertResult("SELECT date('2022-04-05')", datetime.date(2022, 4, 5))
        self.assertError ("SELECT date(NULL)")
        self.assertResult("SELECT date(2022-04-05)", datetime.date(2022, 4, 5))
        self.assertResult("SELECT date(2022, 4, 5)", datetime.date(2022, 4, 5))
        self.assertResult("SELECT date(meta('int'))", None, datetime.date)
        self.assertResult("SELECT date(meta('decimal'))", None, datetime.date)
        self.assertResult("SELECT date(meta('bool'))", None, datetime.date)
        self.assertResult("SELECT date(meta('str'))", None, datetime.date)
        self.assertResult("SELECT date(meta('date'))", datetime.date(2022, 4, 5))
        self.assertResult("SELECT date(meta('null'))", None, datetime.date)
        self.assertResult("SELECT date(meta('missing'))", None, datetime.date)

    def test_operators(self):
        # add
        self.assertResult("SELECT 1 + 1", 2)
        self.assertResult("SELECT 1.0 + 1", Decimal(2))
        self.assertResult("SELECT 1.0 + 2.00", Decimal(3))
        self.assertError ("SELECT 1970-01-01 + 2022-04-01")
        self.assertResult("SELECT 2022-04-01 + 1", datetime.date(2022, 4, 2))
        self.assertResult("SELECT 1 + 2022-04-01", datetime.date(2022, 4, 2))

        # sub
        self.assertResult("SELECT 1 - 1", 0)
        self.assertResult("SELECT 1.0 - 1", Decimal(0))
        self.assertResult("SELECT 1.0 - 2.00", Decimal(-1))
        self.assertResult("SELECT 2022-04-01 - 1", datetime.date(2022, 3, 31))
        self.assertResult("SELECT 2022-04-01 - 2022-03-31", 1)
        self.assertError ("SELECT 1 - 2022-04-01")

        # mul
        self.assertResult("SELECT 2 * 2", 4)
        self.assertResult("SELECT 2.0 * 2", Decimal(4))
        self.assertResult("SELECT 2 * 2.0", Decimal(4))
        self.assertResult("SELECT 2.0 * 2.0", Decimal(4))

        # div
        self.assertResult("SELECT 4 / 2", Decimal(2))
        self.assertResult("SELECT 4.0 / 2", Decimal(2))
        self.assertResult("SELECT 4 / 2.0", Decimal(2))
        self.assertResult("SELECT 4.0 / 2.0", Decimal(2))

        # match
        self.assertResult("SELECT 'foobarbaz' ~ 'bar'", True)
        self.assertResult("SELECT 'foobarbaz' ~ 'quz'", False)

        # and
        self.assertResult("SELECT 1 and FALSE", False)
        self.assertResult("SELECT 'something' and FALSE", False)
        self.assertResult("SELECT 1.0 and FALSE", False)
        self.assertResult("SELECT TRUE and meta('missing')", False)
        self.assertResult("SELECT TRUE and not meta('missing')", True)

        # or
        self.assertResult("SELECT FALSE or 1", True)
        self.assertResult("SELECT FALSE or 'something'", True)
        self.assertResult("SELECT FALSE or 1.0", True)
        self.assertResult("SELECT TRUE or meta('missing')", True)
        self.assertResult("SELECT FALSE or not meta('missing')", True)

        # not
        self.assertResult("SELECT not TRUE", False)
        self.assertResult("SELECT not meta('missing')", True)

        # is null
        self.assertResult("SELECT meta('missing') IS NULL", True)
        self.assertResult("SELECT meta('int') IS NULL", False)
        self.assertResult("SELECT meta('missing') IS NOT NULL", False)
        self.assertResult("SELECT meta('int') IS NOT NULL", True)

        # contains
        self.assertResult("SELECT 'tag' IN tags", False)
        self.assertResult("SELECT 3 IN (2, 3, 4)", True)
        self.assertResult("SELECT 'x' IN ('a', 'b', 'c')", False)

    def test_operators_type_inference(self):
        self.assertResult("SELECT 1 + meta('int')", Decimal(2))
        self.assertResult("SELECT 1 + meta('str3')", Decimal(4))
        self.assertResult("SELECT meta('int') > 0", True)

    def test_functions(self):
        # round
        self.assertResult("SELECT round(1.2)", Decimal(1))
        self.assertResult("SELECT round(1.234, 2)", Decimal('1.23'))
        self.assertResult("SELECT round(12)", 12)
        self.assertResult("SELECT round(12, -1)", 10)

        # commodity_meta
        self.assertResult("SELECT commodity_meta('MISSING')", None, dict)
        self.assertResult("SELECT commodity_meta('TEST')",
                          {'filename': '<string>', 'lineno': 2, 'rate': Decimal('42')})
        self.assertResult("SELECT commodity_meta('TEST', 'rate')", Decimal('42'), object)

    def test_coalesce(self):
        # coalesce
        self.assertResult("SELECT COALESCE(str(meta('missing')), '!')", "!")
        self.assertError ("SELECT COALESCE(meta('missing'), '!')")


class TestFilterEntries(CommonInputBase, QueryBase):

    def test_filter_empty_from(self):
        # Check that no filter outputs the very same thing.
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT * ;
        """).c_from, self.entries, self.options_map, self.context)
        self.assertEqualEntries(self.entries, filtered_entries)

    def test_filter_by_year(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type FROM year(date) = 2012;
        """).c_from, self.entries, self.options_map, self.context)
        self.assertEqualEntries("""

          2012-02-02 * "Dinner with Dos"
            Assets:Bank:Checking              102.00 USD
            Expenses:Restaurant              -102.00 USD

        """, filtered_entries)

    def test_filter_by_expr1(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type
          FROM NOT (type = 'transaction' AND
                    (year(date) = 2012 OR year(date) = 2013));
        """).c_from, self.entries, self.options_map, self.context)
        self.assertEqualEntries("""

          2010-01-01 open Assets:Bank:Checking
          2010-01-01 open Assets:Bank:Savings
          2010-01-01 open Expenses:Restaurant
          2010-01-01 open Assets:ForeignBank:Checking

          2010-01-01 * "Dinner with Cero"
            Assets:Bank:Checking              100.00 USD
            Expenses:Restaurant              -100.00 USD

          2011-01-01 * "Dinner with Uno"
            Assets:Bank:Checking              101.00 USD
            Expenses:Restaurant              -101.00 USD

          2014-04-04 * "Dinner with Quatro"
            Assets:Bank:Checking              104.00 USD
            Expenses:Restaurant              -104.00 USD

        """, filtered_entries)

    def test_filter_by_expr2(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type FROM date < 2012-06-01;
        """).c_from, self.entries, self.options_map, self.context)
        self.assertEqualEntries("""

          2010-01-01 open Assets:Bank:Checking
          2010-01-01 open Assets:Bank:Savings
          2010-01-01 open Expenses:Restaurant
          2010-01-01 open Assets:ForeignBank:Checking

          2010-01-01 * "Dinner with Cero"
            Assets:Bank:Checking              100.00 USD
            Expenses:Restaurant              -100.00 USD

          2011-01-01 * "Dinner with Uno"
            Assets:Bank:Checking              101.00 USD
            Expenses:Restaurant              -101.00 USD

          2012-02-02 * "Dinner with Dos"
            Assets:Bank:Checking              102.00 USD
            Expenses:Restaurant              -102.00 USD

        """, filtered_entries)

    def test_filter_close_undated(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type FROM CLOSE;
        """).c_from, self.entries, self.options_map, self.context)

        self.assertEqualEntries(self.INPUT + textwrap.dedent("""

          2014-04-04 'C "Conversion for (-50.00 USD, -60.00 CAD)"
            Equity:Conversions:Current  50.00 USD @ 0 NOTHING
            Equity:Conversions:Current  60.00 CAD @ 0 NOTHING

        """), filtered_entries)

    def test_filter_close_dated(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type FROM CLOSE ON 2013-06-01;
        """).c_from, self.entries, self.options_map, self.context)
        self.assertEqualEntries(self.entries[:-2], filtered_entries)

    def test_filter_open_dated(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type FROM OPEN ON 2013-01-01;
        """).c_from, self.entries, self.options_map, self.context)

        self.assertEqualEntries("""

          2010-01-01 open Assets:Bank:Checking
          2010-01-01 open Assets:Bank:Savings
          2010-01-01 open Expenses:Restaurant
          2010-01-01 open Assets:ForeignBank:Checking

          2012-12-31 'S "Opening balance for 'Assets:Bank:Checking' (Summarization)"
            Assets:Bank:Checking                                                   303.00 USD
            Equity:Opening-Balances                                               -303.00 USD

          2012-12-31 'S "Opening balance for 'Equity:Earnings:Previous' (Summarization)"
            Equity:Earnings:Previous                                              -303.00 USD
            Equity:Opening-Balances                                                303.00 USD

          2013-03-03 * "Dinner with Tres"
            Assets:Bank:Checking                                                   103.00 USD
            Expenses:Restaurant                                                   -103.00 USD

          2013-10-10 * "International Transfer"
            Assets:Bank:Checking                                                   -50.00 USD                                   ;     -50.00 USD
            Assets:ForeignBank:Checking                                            -60.00 CAD                        @ 1.20 USD ;     -72.00 USD

          2014-04-04 * "Dinner with Quatro"
            Assets:Bank:Checking                                                   104.00 USD
            Expenses:Restaurant                                                   -104.00 USD

        """, filtered_entries)

    def test_filter_clear(self):
        filtered_entries = qx.filter_entries(self.compile("""
          SELECT date, type FROM CLEAR;
        """).c_from, self.entries, self.options_map, self.context)

        self.assertEqualEntries(self.INPUT + textwrap.dedent("""

          2014-04-04 'T "Transfer balance for 'Expenses:Restaurant' (Transfer balance)"
            Expenses:Restaurant                                 510.00 USD
            Equity:Earnings:Current                            -510.00 USD

        """), filtered_entries)


class TestExecutePrint(CommonInputBase, QueryBase):

    def test_print_with_filter(self):
        statement = qc.EvalPrint(
            qc.EvalFrom(
                qc.Operator(qp.Equal, [
                    qe.Column('year'),
                    qc.EvalConstant(2012),
                ]),
                None, None, None))
        oss = io.StringIO()
        qx.execute_print(statement, self.entries, self.options_map, oss)

        self.assertEqualEntries("""

          2012-02-02 * "Dinner with Dos"
            Assets:Bank:Checking                                                   102.00 USD
            Expenses:Restaurant                                                   -102.00 USD

        """, oss.getvalue())

    def test_print_with_no_filter(self):
        statement = qc.EvalPrint(qc.EvalFrom(None, None, None, None))
        oss = io.StringIO()
        qx.execute_print(statement, self.entries, self.options_map, oss)
        self.assertEqualEntries(self.INPUT, oss.getvalue())

        statement = qc.EvalPrint(None)
        oss = io.StringIO()
        qx.execute_print(statement, self.entries, self.options_map, oss)
        self.assertEqualEntries(self.INPUT, oss.getvalue())


class TestAllocation(unittest.TestCase):

    def test_allocator(self):
        allocator = qx.Allocator()
        self.assertEqual(0, allocator.allocate())
        self.assertEqual(1, allocator.allocate())
        self.assertEqual(2, allocator.allocate())
        self.assertEqual([None, None, None], allocator.create_store())


class TestExecuteNonAggregatedQuery(QueryBase):

    INPUT = """

      2010-01-01 open Assets:Bank:Checking
      2010-01-01 open Expenses:Restaurant

      2010-02-23 * "Bla"
        Assets:Bank:Checking       100.00 USD
        Expenses:Restaurant       -100.00 USD

    """

    def test_non_aggregate__one(self):
        self.check_query(
            self.INPUT,
            """
            SELECT date;
            """,
            [('date', datetime.date)],
            [(datetime.date(2010, 2, 23),),
             (datetime.date(2010, 2, 23),)])

    def test_non_aggregate__many(self):
        self.check_query(
            self.INPUT,
            """
            SELECT date, flag, payee, narration;
            """,
            [
                ('date', datetime.date),
                ('flag', str),
                ('payee', str),
                ('narration', str),
                ],
            [
                (datetime.date(2010, 2, 23), '*', None, 'Bla'),
                (datetime.date(2010, 2, 23), '*', None, 'Bla'),
                ])

    def test_non_aggregated_order_by_visible(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account, length(account) ORDER BY 2;
            """,
            [
                ('account', str),
                ('length(account)', int),
                ],
            [
                ('Expenses:Restaurant', 19),
                ('Assets:Bank:Checking', 20),
                ])

    def test_non_aggregated_order_by_invisible(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account ORDER BY length(account);
            """,
            [
                ('account', str),
                ],
            [
                ('Expenses:Restaurant',),
                ('Assets:Bank:Checking',),
                ])

    def test_non_aggregated_order_by_none_date(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account ORDER BY cost_date;
            """,
            [
                ('account', str),
                ],
            [
                ('Assets:Bank:Checking',),
                ('Expenses:Restaurant',),
                ])

    def test_non_aggregated_order_by_none_str(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account ORDER BY posting_flag;
            """,
            [
                ('account', str),
                ],
            [
                ('Assets:Bank:Checking',),
                ('Expenses:Restaurant',),
                ])


class TestExecuteAggregatedQuery(QueryBase):

    INPUT = """

      2010-01-01 open Assets:Bank:Checking
      2010-01-01 open Expenses:Restaurant

      2010-02-23 * "Bla"
        Assets:Bank:Checking       100.00 USD
        Expenses:Restaurant       -100.00 USD

    """

    def test_aggregated_group_by_all_implicit(self):
        # There is no group-by, but all columns are aggregations.
        self.check_query(
            self.INPUT,
            """
            SELECT first(account), last(account);
            """,
            [
                ('first(account)', str),
                ('last(account)', str),
                ],
            [
                ('Assets:Bank:Checking', 'Expenses:Restaurant'),
                ])

    def test_aggregated_group_by_all_explicit(self):
        # All columns ('account', 'len') are subject of a group-by.
        self.check_sorted_query(
            self.INPUT,
            """
            SELECT account, length(account) as len
            GROUP BY account, len;
            """,
            [
                ('account', str),
                ('len', int),
                ],
            [
                ('Assets:Bank:Checking', 20),
                ('Expenses:Restaurant', 19),
                ])

        self.check_sorted_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Restaurant         1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Restaurant         2.00 USD
            """,
            """
            SELECT account, length(account) as len
            GROUP BY account, len;
            """,
            [
                ('account', str),
                ('len', int),
                ],
            [
                ('Assets:Bank:Checking', 20),
                ('Expenses:Restaurant', 19),
                ('Liabilities:Credit-Card', 23),
                ])

    def test_aggregated_group_by_visible(self):
        # GROUP-BY: 'account' is visible.
        self.check_sorted_query(
            self.INPUT,
            """
            SELECT account, sum(position) as amount
            GROUP BY account;
            """,
            [
                ('account', str),
                ('amount', inventory.Inventory),
                ],
            [
                ('Assets:Bank:Checking', inventory.from_string('100.00 USD')),
                ('Expenses:Restaurant', inventory.from_string('-100.00 USD')),
                ])

    def test_aggregated_group_by_invisible(self):
        # GROUP-BY: 'account' is invisible.
        self.check_sorted_query(
            self.INPUT,
            """
            SELECT count(position)
            GROUP BY account;
            """,
            [
                ('count(position)', int),
                ],
            [
                (1,),
                (1,),
                ])

    def test_aggregated_group_by_visible_order_by_non_aggregate_visible(self):
        # GROUP-BY: 'account' is visible.
        # ORDER-BY: 'account' is a non-aggregate and visible.
        self.check_query(
            self.INPUT,
            """
            SELECT account, sum(position) as amount
            GROUP BY account
            ORDER BY account;
            """,
            [
                ('account', str),
                ('amount', inventory.Inventory),
                ],
            [
                ('Assets:Bank:Checking', inventory.from_string('100.00 USD')),
                ('Expenses:Restaurant', inventory.from_string('-100.00 USD')),
                ])

    def test_aggregated_group_by_visible_order_by_non_aggregate_invisible(self):
        # GROUP-BY: 'account' and 'length(account)' are visible.
        # ORDER-BY: 'length(account)' is a non-aggregate and invisible.
        self.check_query(
            self.INPUT,
            """
            SELECT account, sum(position) as amount
            GROUP BY account, length(account)
            ORDER BY length(account);
            """,
            [
                ('account', str),
                ('amount', inventory.Inventory),
                ],
            [
                ('Expenses:Restaurant', inventory.from_string('-100.00 USD')),
                ('Assets:Bank:Checking', inventory.from_string('100.00 USD')),
                ])

    def test_aggregated_group_by_visible_order_by_aggregate_visible(self):
        # GROUP-BY: 'account' is visible.
        # ORDER-BY: 'sum(account)' is an aggregate and visible.
        self.check_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Restaurant         1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Restaurant         2.00 USD
            """,
            """
            SELECT account, count(account) as num, sum(number) as sum
            GROUP BY account
            ORDER BY sum(number);
            """,
            [
                ('account', str),
                ('num', int),
                ('sum', Decimal),
                ],
            [
                ('Liabilities:Credit-Card', 1, D('-2.00')),
                ('Assets:Bank:Checking', 1, D('-1.00')),
                ('Expenses:Restaurant', 2, D('3.00')),
                ])

    def test_aggregated_group_by_visible_order_by_aggregate_invisible(self):
        # GROUP-BY: 'account' is visible.
        # ORDER-BY: 'sum(number)' is an aggregate and invisible.
        self.check_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Restaurant         1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Restaurant         2.00 USD
            """,
            """
            SELECT account, count(account) as num
            GROUP BY account
            ORDER BY sum(number);
            """,
            [
                ('account', str),
                ('num', int),
                ],
            [
                ('Liabilities:Credit-Card', 1),
                ('Assets:Bank:Checking', 1),
                ('Expenses:Restaurant', 2),
                ])

    def test_aggregated_group_by_invisible_order_by_non_aggregate_visible(self):
        # GROUP-BY: 'account' is invisible.
        # ORDER-BY: 'len(account)' is a non-aggregate and visible.
        self.check_query(
            self.INPUT,
            """
            SELECT length(account) as len, sum(position) as amount
            GROUP BY account, len
            ORDER BY len;
            """,
            [
                ('len', int),
                ('amount', inventory.Inventory),
                ],
            [
                (19, inventory.from_string('-100.00 USD'),),
                (20, inventory.from_string('100.00 USD'),),
                ])

    def test_aggregated_group_by_invisible_order_by_non_aggregate_invis(self):
        # GROUP-BY: 'account' is invisible.
        # ORDER-BY: 'sum(number)' is an aggregate and invisible.
        self.check_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Restaurant         1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Restaurant         2.00 USD
            """,
            """
            SELECT count(account) as num
            GROUP BY account
            ORDER BY sum(number);
            """,
            [
                ('num', int),
                ],
            [
                (1,),
                (1,),
                (2,),
                ])

    def test_aggregated_group_by_invisible_order_by_aggregate_visible(self):
        # GROUP-BY: 'account' is invisible.
        # ORDER-BY: 'sum(account)' is an aggregate and visible.
        self.check_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Restaurant         1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Restaurant         2.00 USD
            """,
            """
            SELECT count(account) as num, sum(number) as sum
            GROUP BY account
            ORDER BY sum(number);
            """,
            [
                ('num', int),
                ('sum', Decimal),
                ],
            [
                (1, D('-2.00')),
                (1, D('-1.00')),
                (2, D('3.00')),
                ])

    def test_aggregated_group_by_invisible_order_by_aggregate_invisible(self):
        # GROUP-BY: 'account' is invisible.
        # ORDER-BY: 'sum(number)' is an aggregate and invisible.
        self.check_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Restaurant         1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Restaurant         2.00 USD
            """,
            """
            SELECT count(account) as num
            GROUP BY account
            ORDER BY sum(number);
            """,
            [
                ('num', int),
                ],
            [
                (1,),
                (1,),
                (2,),
                ])

    def test_aggregated_group_by_with_having(self):
        self.check_query(
            """
            2010-02-21 * "First"
              Assets:Bank:Checking       -1.00 USD
              Expenses:Foo                1.00 USD

            2010-02-23 * "Second"
              Liabilities:Credit-Card    -2.00 USD
              Expenses:Bar                2.00 USD
            """,
            """
            SELECT account, sum(number)
            GROUP BY account
            HAVING sum(number) > 0.0
            ORDER BY account
            """,
            [
                ('account', str),
                ('sum(number)', Decimal),
            ],
            [
                ('Expenses:Bar', D(2.0)),
                ('Expenses:Foo', D(1.0)),
            ])


class TestExecuteOptions(QueryBase):

    INPUT = """

      2010-02-23 *
        Assets:AssetA       5.00 USD
        Assets:AssetD       2.00 USD
        Assets:AssetB       4.00 USD
        Assets:AssetC       3.00 USD
        Assets:AssetE       1.00 USD
        Equity:Rest       -15.00 USD

    """

    def test_order_by_asc_implicit(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account, number ORDER BY number;
            """,
            [
                ('account', str),
                ('number', Decimal),
                ],
            [
                ('Equity:Rest', D('-15.00')),
                ('Assets:AssetE', D('1.00')),
                ('Assets:AssetD', D('2.00')),
                ('Assets:AssetC', D('3.00')),
                ('Assets:AssetB', D('4.00')),
                ('Assets:AssetA', D('5.00')),
                ])

    def test_order_by_asc_explicit(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account, number ORDER BY number ASC;
            """,
            [
                ('account', str),
                ('number', Decimal),
                ],
            [
                ('Equity:Rest', D('-15.00')),
                ('Assets:AssetE', D('1.00')),
                ('Assets:AssetD', D('2.00')),
                ('Assets:AssetC', D('3.00')),
                ('Assets:AssetB', D('4.00')),
                ('Assets:AssetA', D('5.00')),
                ])

    def test_order_by_desc(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account, number ORDER BY number DESC;
            """,
            [
                ('account', str),
                ('number', Decimal),
                ],
            [
                ('Assets:AssetA', D('5.00')),
                ('Assets:AssetB', D('4.00')),
                ('Assets:AssetC', D('3.00')),
                ('Assets:AssetD', D('2.00')),
                ('Assets:AssetE', D('1.00')),
                ('Equity:Rest', D('-15.00')),
                ])

    def test_distinct(self):
        self.check_sorted_query(
            """
              2010-02-23 *
                Assets:AssetA       5.00 USD
                Assets:AssetA       2.00 USD
                Assets:AssetA       4.00 USD
                Equity:Rest
            """,
            """
            SELECT account ;
            """,
            [
                ('account', str),
                ],
            [
                ('Assets:AssetA',),
                ('Assets:AssetA',),
                ('Assets:AssetA',),
                ('Equity:Rest',),
                ])

        self.check_sorted_query(
            """
              2010-02-23 *
                Assets:AssetA       5.00 USD
                Assets:AssetA       2.00 USD
                Assets:AssetA       4.00 USD
                Equity:Rest        -5.00 USD
                Equity:Rest        -2.00 USD
                Equity:Rest        -4.00 USD
            """,
            """
            SELECT DISTINCT account ;
            """,
            [
                ('account', str),
                ],
            [
                ('Assets:AssetA',),
                ('Equity:Rest',),
                ])

    def test_limit(self):
        self.check_query(
            self.INPUT,
            """
            SELECT account, number ORDER BY number LIMIT 3;
            """,
            [
                ('account', str),
                ('number', Decimal),
                ],
            [
                ('Equity:Rest', D('-15.00')),
                ('Assets:AssetE', D('1.00')),
                ('Assets:AssetD', D('2.00')),
                ])


class TestOrderBy(QueryBase):
    data = """

    2022-03-28 * "Test"
      Assets:Tests  1.00 USD
        aa: 1
        bb: 1
      Assets:Tests  2.00 USD
        aa: 1
        bb: 2
      Assets:Tests  3.00 USD
        aa: 2
      Assets:Tests  4.00 USD
        aa: 2
        bb: 1
      Expenses:Tests

    """

    def test_order_by_asc_asc(self):
        self.check_query(self.data,
            """SELECT account, meta('aa') AS a, meta('bb') AS b ORDER BY 2, 3""",
            [
                ('account', str), ('a', object), ('b', object)
            ],
            [
                ('Expenses:Tests', None, None),
                ('Assets:Tests', 1, 1),
                ('Assets:Tests', 1, 2),
                ('Assets:Tests', 2, None),
                ('Assets:Tests', 2, 1),
            ])

    def test_order_by_asc_desc(self):
        self.check_query(self.data,
            """SELECT account, meta('aa') AS a, meta('bb') AS b ORDER BY 2, 3 DESC""",
            [
                ('account', str), ('a', object), ('b', object)
            ],
            [
                ('Expenses:Tests', None, None),
                ('Assets:Tests', 1, 2),
                ('Assets:Tests', 1, 1),
                ('Assets:Tests', 2, 1),
                ('Assets:Tests', 2, None),
            ])

    def test_order_by_desc_asc(self):
        self.check_query(self.data,
            """SELECT account, meta('aa') AS a, meta('bb') AS b ORDER BY 2 DESC, 3""",
            [
                ('account', str), ('a', object), ('b', object)
            ],
            [
                ('Assets:Tests', 2, None),
                ('Assets:Tests', 2, 1),
                ('Assets:Tests', 1, 1),
                ('Assets:Tests', 1, 2),
                ('Expenses:Tests', None, None),
            ])

    def test_order_by_desc_desc(self):
        self.check_query(self.data,
            """SELECT account, meta('aa') AS a, meta('bb') AS b ORDER BY 2 DESC, 3 DESC""",
            [
                ('account', str), ('a', object), ('b', object)
            ],
            [
                ('Assets:Tests', 2, 1),
                ('Assets:Tests', 2, None),
                ('Assets:Tests', 1, 2),
                ('Assets:Tests', 1, 1),
                ('Expenses:Tests', None, None),
            ])


class TestArithmeticFunctions(QueryBase):

    # You need some transactions in order to eval a simple arithmetic op.
    # This also properly sets the data type to Decimal.
    # In v2, revise this so that this works like a regular DB and support integers.

    def test_add(self):
        self.check_query(
            """
              2010-02-23 *
                Assets:Something       5.00 USD
            """,
            """
              SELECT number + 3 as result;
            """,
            [('result', Decimal)],
            [(D("8"),)])

    def test_sub(self):
        self.check_query(
            """
              2010-02-23 *
                Assets:Something       5.00 USD
            """,
            """
              SELECT number - 3 as result;
            """,
            [('result', Decimal)],
            [(D("2"),)])

    def test_mul(self):
        self.check_query(
            """
              2010-02-23 *
                Assets:Something       5.00 USD
            """,
            """
              SELECT number * 1.2 as result;
            """,
            [('result', Decimal)],
            [(D("6"),)])

    def test_div(self):
        self.check_query(
            """
              2010-02-23 *
                Assets:Something       5.00 USD
            """,
            """
              SELECT number / 2 as result;
            """,
            [('result', Decimal)],
            [(D("2.50"),)])

        # Test dbz, should fail result query.
        with self.assertRaises(decimal.DivisionByZero):
            self.check_query(
                """
                  2010-02-23 *
                    Assets:Something       5.00 USD
                """,
                """
                  SELECT number / 0 as result;
                """,
                [('result', Decimal)],
                [(D("2.50"),)])

    def test_safe_div(self):
        self.check_query(
            """
              2010-02-23 *
                Assets:Something       5.00 USD
            """,
            """
              SELECT SAFEDIV(number, 0) as result;
            """,
            [('result', Decimal)],
            [(D("0"),)])

    def test_safe_div_zerobyzero(self):
        self.check_query(
            """
              2010-02-23 *
                Assets:Something       5.00 USD
            """,
            """
              SELECT SAFEDIV(0.0, 0) as result;
            """,
            [('result', Decimal)],
            [(D("0"),)])


class TestExecutePivot(QueryBase):

    def setUp(self):
        super().setUp()
        self.entries, errors, self.options = loader.load_string(self.data, dedent=True)
        self.assertFalse(errors)

    def execute(self, query):
        query = self.compile(query)
        return qx.execute_query(query, self.entries, self.options)

    data = """
      2012-01-01 open Assets:Cash
      2012-01-01 open Expenses:Aaa
      2012-01-01 open Expenses:Bbb

      2012-01-01 * "Test"
        Expenses:Bbb  1.00 USD
        Assets:Cash

      2012-01-01 * "Test"
        Expenses:Aaa  2.00 USD
        Assets:Cash

      2012-02-02 * "Test"
        Expenses:Aaa  3.00 USD
        Assets:Cash

      2013-01-01 * "Test"
        Expenses:Aaa  4.00 USD
        Assets:Cash

      2014-02-02 * "Test"
        Expenses:Bbb  5.00 USD
        Assets:Cash

      2014-03-03 * "Test"
        Expenses:Aaa  6.00 USD
        Assets:Cash

      2013-01-01 * "Test"
        Expenses:Bbb  7.00 USD
        Assets:Cash

      2015-04-04 * "Test"
        Expenses:Aaa  8.00 USD
        Assets:Cash
    """

    def test_pivot_one_column(self):
        self.assertEqual(self.execute("""
            SELECT
              account,
              year(date) AS year,
              sum(cost(position)) AS balance
            WHERE
              account ~ 'Expenses'
            GROUP BY 1, 2
            PIVOT BY 1, 2"""), (
            [
                ('account/year', str),
                ('2012', inventory.Inventory),
                ('2013', inventory.Inventory),
                ('2014', inventory.Inventory),
                ('2015', inventory.Inventory),
            ],
            [
                ('Expenses:Aaa', I('5.00 USD'), I('4.00 USD'), I('6.00 USD'), I('8.00 USD')),
                ('Expenses:Bbb', I('1.00 USD'), I('7.00 USD'), I('5.00 USD'), None),
            ]))

    def test_pivot_one_column_by_name(self):
        self.assertEqual(self.execute("""
            SELECT
              account,
              year(date) AS year,
              sum(cost(position)) AS balance
            WHERE
              account ~ 'Expenses'
            GROUP BY 1, 2
            PIVOT BY account, year"""), (
            [
                ('account/year', str),
                ('2012', inventory.Inventory),
                ('2013', inventory.Inventory),
                ('2014', inventory.Inventory),
                ('2015', inventory.Inventory),
            ],
            [
                ('Expenses:Aaa', I('5.00 USD'), I('4.00 USD'), I('6.00 USD'), I('8.00 USD')),
                ('Expenses:Bbb', I('1.00 USD'), I('7.00 USD'), I('5.00 USD'), None),
            ]))

    def test_pivot_two_column(self):
        self.assertEqual(self.execute("""
            SELECT
              account,
              year(date) AS year,
              sum(cost(position)) AS balance,
              last(date) AS updated
            WHERE
              account ~ 'Expenses' AND
              year >= 2014
            GROUP BY 1, 2
            PIVOT BY 1, 2"""), (
            [
                ('account/year', str),
                ('2014/balance', inventory.Inventory),
                ('2014/updated', datetime.date),
                ('2015/balance', inventory.Inventory),
                ('2015/updated', datetime.date),
            ],
            [
                ('Expenses:Aaa', I('6.00 USD'), datetime.date(2014, 3, 3), I('8.00 USD'), datetime.date(2015, 4, 4)),
                ('Expenses:Bbb', I('5.00 USD'), datetime.date(2014, 2, 2), None, None),
            ]))

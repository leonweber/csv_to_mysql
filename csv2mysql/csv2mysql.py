import csv
import os
import string
from datetime import datetime

import click

NULL_CANDIDATES = {"", "null", "-"}
DATE_CANDIDATES = ["%b %d, %Y", "%Y-%M-%d"]
TRUE_VALUES = {'t', '1', 'yes', 'true'}
FALSE_VALUES = {'f', '0', 'no', 'false'}
VARCHAR_MAX_SIZE = 100
MAX_ROW_LENGTH = 65535


class Column:
    def __init__(self, name, transformation=None):
        self.name = None
        self.set_name(name)
        self.values = []
        self.transformation = transformation
        self.type = None
        self.null_symbol = None
        self.bool_pair = None
        self.date_format = None

    def __str__(self):
        return "{}: <{}>".format(self.name, self.type)

    def __repr__(self):
        return self.__str__()

    def set_name(self, name):
        name = name.lower()
        normalized_name = ""
        for char in name:
            if char in string.ascii_letters:
                normalized_name += char
            else:
                normalized_name += " "
        normalized_name = normalized_name.strip()
        normalized_name = normalized_name.replace(" ", "_")
        self.name = normalized_name

    def infer_type(self):
        if self.is_none():
            self.type = "longtext"
            return

        if self.is_int():
            self.type = "int"
            return

        if self.is_bool():
            self.type = "bool"
            return

        if self.is_float():
            self.type = "float"
            return

        if self.is_date():
            self.type = "date"
            return

        if self.is_varchar():
            self.type = "varchar"
        else:
            self.type = "longtext"

    def is_none(self):
        return all([v == '' for v in self.values])

    def is_int(self):
        null_candidate = None
        max_value = None
        for value in self.values:
            try:
                if max_value is None:
                    max_value = int(value)
                else:
                    max_value = max(int(value), max_value)
            except ValueError:
                if null_candidate is None:
                    null_candidate = value
                elif null_candidate != value:
                    return False
        if max_value > 1:
            self.null_symbol = null_candidate
            return True
        else:
            return False

    def is_float(self):
        null_candidate = None
        for value in self.values:
            try:
                float(value)
            except ValueError:
                if null_candidate is None:
                    null_candidate = value
                elif null_candidate != value:
                    return False

        self.null_symbol = null_candidate
        return True

    def is_date(self):
        null_candidate = None
        date_format = None
        for value in self.values:
            value = value.strip().lower()
            if date_format is None:
                for format_candidate in DATE_CANDIDATES:
                    if self.fits_date_format(value,
                                             format_candidate):
                        date_format = format_candidate
                        null_candidate = None
                    elif null_candidate is None:
                        null_candidate = value
                if date_format is None and null_candidate != value:
                    return False
            else:
                if not self.fits_date_format(value, date_format):
                    if null_candidate is None:
                        null_candidate = value
                    elif null_candidate != value:
                        return False

        self.date_format = date_format
        return True

    @staticmethod
    def fits_date_format(possible_date, date_format):
        try:
            datetime.strptime(possible_date,
                              date_format)
        except ValueError:
            return False
        return True

    def is_bool(self):
        null_candidate = None
        true_value = None
        false_value = None
        for value in self.values:
            value = value.strip().lower()
            if value not in TRUE_VALUES | FALSE_VALUES:
                if null_candidate is None:
                    null_candidate = value
                elif null_candidate != value:
                    return False
            else:
                if value in TRUE_VALUES:
                    true_value = value
                else:
                    false_value = value
        self.bool_pair = (true_value, false_value)
        self.null_symbol = null_candidate
        return True

    def is_varchar(self):
        max_length = 0
        null_value = None
        for value in self.values:
            if value in NULL_CANDIDATES:
                null_value = null_value
            max_length = max(len(value), max_length)

        self.null_symbol = null_value
        if max_length < VARCHAR_MAX_SIZE:
            return True
        else:
            return False


class Transformer:
    def __init__(self, in_file, out_file, table_name="",
                 sniff_size=1000, generate_drop_table=True,
                 generate_create_table=True,
                 generate_load_data=True):
        self.in_file = os.path.abspath(in_file)
        self.out_file = out_file
        self.sniff_size = sniff_size
        self.table_name = table_name
        self.generate_drop_table = generate_drop_table
        self.generate_create_table = generate_create_table
        self.generate_load_data = generate_load_data

        self.dialect = None
        self.columns = []
        self.build_columns()

    def build_columns(self):
        with open(self.in_file) as f:
            self.dialect = csv.Sniffer().sniff(f.read(1024))
            f.seek(0)
            reader = csv.reader(f, self.dialect)

            self.columns = []
            header = next(reader)
            for column_name in header:
                self.columns.append(Column(column_name))

            for linum, row in enumerate(reader, start=1):
                if linum > self.sniff_size:
                    break

                for column_number, value in enumerate(row):
                    self.columns[column_number].values.append(value)

            for column in self.columns:
                column.infer_type()

    def get_varchar_size(self):
        return int(MAX_ROW_LENGTH / len(self.columns))

    def get_drop_table(self):
        sql_str = "DROP TABLE IF EXISTS {};".format(self.table_name)
        return sql_str

    def get_create_table(self):
        sql_str = "CREATE TABLE {}(\n".format(self.table_name)
        for column_num, column in enumerate(self.columns):
            if column.type == "varchar":
                column_type = "VARCHAR({})".format(
                    self.get_varchar_size())
            else:
                column_type = column.type.upper()

            if column_num == len(self.columns) - 1:
                sql_str += "\t{} {}".format(column.name,
                                            column_type)
            else:
                sql_str += "\t{} {},\n".format(column.name,
                                               column_type)
        sql_str += "\n);"

        return sql_str

    def get_load_header(self):
        line_terminator = self.dialect.lineterminator
        if line_terminator == "\n":
            line_terminator = "\\n"
        elif line_terminator == "\r":
            line_terminator = "\\r"
        elif line_terminator == "\r\n":
            line_terminator = "\\r\\n"
        sql_str = ("LOAD DATA INFILE '{}'\n"
                   "INTO TABLE {}\n"
                   "FIELDS TERMINATED BY '{}' "
                   "OPTIONALLY ENCLOSED BY '{}'\n"
                   "LINES TERMINATED BY '{}'\n"
                   "IGNORE 1 LINES"
                   ).format(self.in_file,
                            self.table_name,
                            self.dialect.delimiter,
                            self.dialect.quotechar,
                            line_terminator)
        return sql_str

    def get_load_column_names(self):
        sql_str = "(\n"
        for column_num, column in enumerate(self.columns):
            if column_num == len(self.columns) - 1:
                sql_str += "\t@{}\n".format(column.name)
            else:
                sql_str += "\t@{},\n".format(column.name)
        sql_str += ")"
        return sql_str

    def get_load_set_statements(self):
        set_statement = "SET\n"
        for column_num, column in enumerate(self.columns):
            if column.type == "bool":
                set_statement += "{} = {}".format(
                    column.name,
                    self.get_bool_set_expression(column)
                )
            elif column.type == "date":
                set_statement += "{} = {}".format(
                    column.name,
                    self.get_date_set_expression(column)
                )
            else:
                set_statement += "{} = NULLIF(@{}, '{}')".format(
                    column.name,
                    column.name,
                    column.null_symbol
                )
            if column_num == len(self.columns) - 1:
                set_statement += "\n"
            else:
                set_statement += ",\n"

        return set_statement

    def write_to_outfile(self):
        result_strings = []
        if self.generate_drop_table:
            result_strings.append(self.get_drop_table())
        if self.generate_create_table:
            result_strings.append(self.get_create_table())
        if self.generate_load_data:
            result_strings += [
                self.get_load_header(),
                self.get_load_column_names(),
                self.get_load_set_statements()
            ]
        sql_str = "\n".join(result_strings) + ";"
        with open(self.out_file, "w") as f:
            f.write(sql_str)

    @staticmethod
    def get_bool_set_expression(column):
        true_symbol, false_symbol = column.bool_pair
        sql_str = """IF({} IN ('{}', '{}'),
            IF(@{}='{}', TRUE, FALSE),
            NULL)""".format(column.name, true_symbol, false_symbol,
                            column.name, true_symbol)
        return sql_str

    @staticmethod
    def get_date_set_expression(column):
        sql_str = "str_to_date(@{}, '{}')".format(column.name,
                                                  column.date_format)
        return sql_str


@click.command()
@click.argument("csvfile")
@click.argument("outfile")
@click.argument("tablename")
@click.option("--sniffsize", default=1000,
              help="Number of rows to look at for inferring schema.")
@click.option("--no-createtable", is_flag=True,
              help="Do not generate a CREATE TABLE statement.")
@click.option("--no-droptable", is_flag=True,
              help="Do not generate a DROP TABLE statement.")
@click.option("--no-loaddata", is_flag=True,
              help="Do not generate a LOAD DATA statement.")
def main(csvfile, outfile, tablename, sniffsize, no_droptable,
         no_createtable, no_loaddata):
    """
    Generate a SQL script that loads data from a CSV file.
    """
    transformer = Transformer(in_file=csvfile,
                              out_file=outfile,
                              table_name=tablename,
                              sniff_size=sniffsize,
                              generate_drop_table=not no_droptable,
                              generate_create_table=not no_createtable,
                              generate_load_data=not no_loaddata
                              )
    transformer.write_to_outfile()
    

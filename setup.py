from setuptools import setup

setup(
    name="csv2mysql",
    packages=["csv2mysql"],
    version="0.0.1",
    description="Generate MYSQL scripts to load csv files",
    author="Leon Weber",
    author_email="leonweber@posteo.de",
    url="https://github.com/leonweber/csv_to_mysql",
    keywords=["sql", "mysql", "csv", "conversion", "convert"],
    license='GPLv3',
    classifiers=["Development Status :: 3 - Alpha"],
    install_requires=["click"],
    entry_points={
        "console_scripts": ["csv2mysql = csv2mysql.csv2mysql:main"]
    }
)

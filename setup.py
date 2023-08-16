from setuptools import setup, find_packages

setup(
    name = "docuware-client",
    version = "0.2.2",
    description = "DocuWare REST-API client",
    long_description = open("README.md").read(),
    long_description_content_type = "text/markdown",
    url = "https://github.com/sniner/docuware-client",
    author = "Stefan Schönberger",
    author_email = "mail@sniner.dev",
    install_requires=[
        "requests>=2.27",
    ],
    packages = find_packages(),
    entry_points = {
        "console_scripts": [
            "dw-client = docuware.cli.dw:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    platforms = "any",
    python_requires = ">=3.9",
)

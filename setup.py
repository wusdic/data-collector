"""
DataCollector 安装脚本
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="data-collector",
    version="1.0.0",
    author="吴博",
    author_email="",
    description="自动化资料收集与管理系统",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/wubo-ai/data-collector",
    packages=find_packages(exclude=["tests", "examples"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "PyYAML>=6.0",
        "flask>=2.3.0",
        "flask-cors>=4.0.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
        "python-docx>=0.8.11",
        "openpyxl>=3.1.0",
    ],
    extras_require={
        "pdf": ["PyMuPDF>=1.22.0"],
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "data-collector=main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "data_collector": ["config/*.yaml"],
    },
)

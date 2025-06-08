# CRM & HRM Portal

A comprehensive web-based Customer Relationship Management (CRM) and Human Resource Management (HRM) system built using Django. This portal empowers organizations to efficiently manage their customers, employees, projects, and HR-related operations through a unified platform.

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Usage](#-usage)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

### 🏢 CRM Module
- **Customer Management**: Complete customer registration and profile management
- **Lead Tracking**: Monitor lead progress and conversion rates
- **Communication Logs**: Track all customer interactions and communications
- **Project Assignment**: Assign and manage client projects and tasks

### 👥 HRM Module
- **Employee Management**: Comprehensive employee registration and profile management
- **Attendance System**: Real-time attendance tracking and monitoring
- **Leave Management**: Streamlined leave application and approval workflow
- **Organizational Structure**: Department and role management system
- **Payroll Integration**: Basic payroll structure and management

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Django (Python) |
| **Frontend** | Django Templates, HTML5, CSS3, Bootstrap |
| **Database** | PostgreSQL |
| **Authentication** | Django built-in user authentication |
| **Admin Panel** | Customized Django Admin |

## 📁 Project Structure

```
CRM/
├── base/                          # CRM Application Module
│   ├── templates/                 # HTML templates for CRM
│   ├── migrations/                # Database migrations
│   ├── forms.py                   # Django forms for CRM
│   ├── models.py                  # Database models for CRM
│   ├── views.py                   # View logic for CRM
│   ├── urls.py                    # URL routes for CRM
│   ├── admin.py                   # CRM models admin configuration
│   └── apps.py                    # App configuration for CRM
│
├── hrm/                           # HRM Application Module
│   ├── templates/hrm/             # HTML templates for HRM
│   ├── migrations/                # Database migrations
│   ├── forms.py                   # Django forms for HRM
│   ├── models.py                  # Database models for HRM
│   ├── views.py                   # View logic for HRM
│   ├── urls.py                    # URL routes for HRM
│   ├── admin.py                   # HRM models admin configuration
│   └── apps.py                    # App configuration for HRM
│
├── my_env/                        # Virtual environment (excluded from git)
│
├── project/                       # Main Django Project Configuration
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py                # Global Django settings
│   ├── urls.py                    # Root URL configuration
│   └── wsgi.py
│
├── .gitignore                     # Git ignore file
├── requirements.txt               # Python dependencies
└── manage.py                      # Django management script
```

## 🔧 Prerequisites

Before you begin, ensure you have the following installed on your system:

- **Python 3.8+** - [Download Python](https://python.org/downloads/)
- **pip** - Python package manager (comes with Python)
- **virtualenv** - For Python environment isolation
- **PostgreSQL** or **SQLite** - Database system
- **Git** - Version control system

### Verify Installation

```bash
python --version
pip --version
git --version
```

## 🚀 Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/shauryasawai/CRM.git
cd CRM
```

### Step 2: Set Up Virtual Environment

Create and activate a virtual environment to isolate project dependencies:

#### Create Virtual Environment
```bash
python -m venv my_env
```

#### Install virtualenv (if not already installed)
```bash
pip install virtualenv
```

#### Activate Virtual Environment

**Windows:**
```bash
my_env\Scripts\activate
```

**macOS/Linux:**
```bash
source my_env/bin/activate
```

> 💡 **Note**: You should see `(my_env)` in your terminal prompt when the virtual environment is active.

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Database Setup

#### Apply Migrations
```bash
python manage.py migrate
```

#### Create Superuser (Optional)
```bash
python manage.py createsuperuser
```

### Step 5: Start the Development Server

```bash
python manage.py runserver
```

🎉 **Success!** Your application is now running at `http://127.0.0.1:8000/`

## 🖥 Usage

### Accessing the Application

- **Main Portal**: `http://127.0.0.1:8000/`
- **Admin Panel**: `http://127.0.0.1:8000/admin/`
- **CRM Module**: `http://127.0.0.1:8000/crm/`
- **HRM Module**: `http://127.0.0.1:8000/hrm/`

### Default Login Credentials

After creating a superuser, use those credentials to access the admin panel and manage the system.

## 🔌 Deactivating Virtual Environment

When you're done working on the project:

```bash
deactivate
```

## 🐛 Troubleshooting

### Common Issues and Solutions

**Issue**: `pip` command not found
```bash
python -m pip install --upgrade pip
```

**Issue**: Migration errors
```bash
python manage.py makemigrations
python manage.py migrate --run-syncdb
```

**Issue**: Port already in use
```bash
python manage.py runserver 8001
```

## 📝 Additional Notes

- Ensure you have the latest version of pip: `pip install --upgrade pip`
- The virtual environment (`my_env/`) should not be committed to version control
- Check error messages carefully and ensure all prerequisites are met
- For production deployment, configure proper database settings and security measures

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

If you encounter any issues or have questions, please:

1. Check the [troubleshooting section](#-troubleshooting)
2. Search existing issues on GitHub
3. Create a new issue with detailed information about your problem

---

**Made with ❤️ using Django**

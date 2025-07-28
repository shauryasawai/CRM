# CRM & HRM Portal

A comprehensive web-based Customer Relationship Management (CRM) and Human Resource Management (HRM) system built using Django. This portal empowers organizations to efficiently manage their customers, employees, projects, and HR-related operations through a unified platform. The system provides complete lead-to-client conversion workflows, detailed interaction tracking, service request management, and comprehensive HR functionalities including attendance, leave management, and reimbursement claims.

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

#### Lead Management System
- **Comprehensive Lead Tracking**: Complete lead registration with auto-generated Lead IDs, capturing lead source (existing client, own circle, social media, or other sources)
- **Lead Status Management**: Automatic status progression from "New Lead" to "Cold/Warm/Hot Lead" based on interactions
- **Hierarchical Lead Assignment**: Multi-level lead allocation system with proper hierarchy maintenance
- **First Interaction Tracking**: Mandatory next interaction date setting with detailed product discussion tracking
- **Lead Conversion**: Streamlined lead-to-client conversion process with manager approval workflow

#### Client Relationship Management
- **Detailed Interaction Logging**: Comprehensive interaction tracking with multiple communication modes (Email, Call, Video Meet, WhatsApp, Face-to-Face)
- **Product Discussion Tracking**: Support for 11 different product categories including Mutual Funds, Equity Portfolios, Bonds, Insurance, PMS, AIF, and Structures
- **AI-Powered Summaries**: Integrated Gemini/ChatGPT API for automatic interaction summarization
- **Business Pipeline Management**: Track discussion stages (Cold/Warm/Hot) with expected business values and closure dates
- **Service Request Integration**: Seamless service request creation directly from client interactions

#### Service Request Management
- **Comprehensive Service Types**: Support for Personal Details Modification, Account Creation/Closure, Adhoc Requests for MF & Demat, and Report Requests
- **Multi-Stage Workflow**: Complete request lifecycle from submission to resolution with document management
- **Hierarchical Assignment**: Proper mapping between sales team and operations team with escalation mechanisms
- **Real-time Status Tracking**: Live updates on service request progress with automated notifications

#### Client Profile Management
- **Centralized Client Database**: Complete client profile management with KYC details, investment history, and account mappings
- **Multiple Account Support**: Integration with MFU, Motilal Demat, and Prabhudas Lilladher systems
- **Secure Modification Process**: Controlled client data modification with proper approval workflows
- **Client Lifecycle Management**: Complete client journey from lead conversion to account maintenance

#### Execution Plans
- **Portfolio Review Tool**: Excel-based execution planning for client portfolio optimization
- **Interactive Plan Creation**: Dynamic scheme selection with market value display and operation planning
- **Approval Workflow**: Multi-level approval system for execution plans before client communication
- **Progress Tracking**: Real-time execution tracking with operations team collaboration
- **Plan History**: Complete audit trail of all execution plans and their outcomes

### 👥 HRM Module

#### Leave Management System
- **Interactive Calendar**: Visual holiday calendar with leave planning capabilities
- **Multiple Leave Types**: Support for Privilege, Sick, Special, Maternity, and Paternity leave
- **Automated Approval**: Smart approval routing with auto-approval for delayed requests
- **Leave Cancellation**: Flexible leave cancellation system even post-leave dates
- **Quota Management**: Hierarchy-based leave quota system with real-time balance tracking

#### Attendance Management
- **Location-Based Marking**: GPS-enabled attendance with 500-meter office radius verification
- **Work From Home Support**: Dedicated WFH attendance marking option
- **Monthly Summaries**: Comprehensive attendance reports with red-flag identification
- **Real-time Monitoring**: Live attendance tracking for management oversight

#### Reimbursement System
- **Expense Categorization**: Multiple expense types including Client Meet, Daily Travel, and custom categories
- **Monthly Submission**: Structured monthly expense reporting with real-time entry capability
- **Approval Workflow**: Two-tier approval system through line manager to top management
- **Audit Trail**: Complete expense tracking with remarks and justification requirements

### 📝 Notes Section
- **Personal Productivity Tool**: Private note-taking system with complete confidentiality
- **Organized Lists**: Category-based note organization with custom list creation
- **Reminder System**: Built-in reminder and due date functionality
- **File Attachments**: Support for document attachments up to 500KB
- **Task Management**: Microsoft To-Do inspired interface for personal task tracking

### 📊 Advanced Reporting & Analytics
- **Lead Analytics**: Comprehensive lead conversion ratios, pipeline analysis, and performance metrics
- **Time-to-Conversion Tracking**: Detailed analytics on lead conversion timelines
- **Product-wise Analysis**: Performance tracking across all 11 product categories
- **Hierarchical Reporting**: Role-based reporting with appropriate data visibility
- **Quarterly & Annual Insights**: Time-based performance analysis with trend identification

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Django (Python) |
| **Frontend** | Django Templates, HTML5, CSS3, Bootstrap |
| **Database** | PostgreSQL |
| **Authentication** | Django built-in user authentication with role-based access |
| **AI Integration** | Gemini/ChatGPT API for interaction summaries |
| **Admin Panel** | Customized Django Admin with hierarchical permissions |
| **File Management** | Excel generation and document attachment support |

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

### Key User Roles & Permissions

The system supports multiple hierarchical user roles:
- **Top Management**: Full system access with delete permissions and final approvals
- **Business Head**: Department-level management with approval authorities
- **Team Lead**: Team management with lead allocation and service oversight
- **Relationship Manager (RM)**: Client interaction and lead management
- **Operations Executive**: Service request handling and client profile management

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
- The system maintains comprehensive audit trails and deletion logs for compliance
- AI-powered features require valid API keys for Gemini/ChatGPT integration

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

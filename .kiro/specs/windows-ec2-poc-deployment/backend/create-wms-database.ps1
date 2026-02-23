# Create WMS Database with Sample Data
# Run this after install-sqlserver.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Creating WMS Database" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$connectionString = "Server=localhost\SQLEXPRESS;User Id=sa;Password=Made4Net2026!;TrustServerCertificate=True"

# SQL Script to create database and tables
$sqlScript = @"
-- Create Database
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'WMS_POC')
BEGIN
    CREATE DATABASE WMS_POC;
END
GO

USE WMS_POC;
GO

-- Create Users table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
BEGIN
    CREATE TABLE Users (
        UserId INT PRIMARY KEY IDENTITY(1,1),
        Username NVARCHAR(50) NOT NULL UNIQUE,
        PasswordHash NVARCHAR(255) NOT NULL,
        FullName NVARCHAR(100),
        Email NVARCHAR(100),
        Role NVARCHAR(50),
        CreatedDate DATETIME DEFAULT GETDATE(),
        IsActive BIT DEFAULT 1
    );
END
GO

-- Create Products table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Products')
BEGIN
    CREATE TABLE Products (
        ProductId INT PRIMARY KEY IDENTITY(1,1),
        SKU NVARCHAR(50) NOT NULL UNIQUE,
        ProductName NVARCHAR(200) NOT NULL,
        Description NVARCHAR(500),
        Category NVARCHAR(100),
        UnitPrice DECIMAL(10,2),
        CreatedDate DATETIME DEFAULT GETDATE()
    );
END
GO

-- Create Locations table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Locations')
BEGIN
    CREATE TABLE Locations (
        LocationId INT PRIMARY KEY IDENTITY(1,1),
        LocationCode NVARCHAR(50) NOT NULL UNIQUE,
        Aisle NVARCHAR(10),
        Rack NVARCHAR(10),
        Shelf NVARCHAR(10),
        Capacity INT,
        LocationType NVARCHAR(50)
    );
END
GO

-- Create Inventory table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Inventory')
BEGIN
    CREATE TABLE Inventory (
        InventoryId INT PRIMARY KEY IDENTITY(1,1),
        ProductId INT FOREIGN KEY REFERENCES Products(ProductId),
        LocationId INT FOREIGN KEY REFERENCES Locations(LocationId),
        Quantity INT NOT NULL DEFAULT 0,
        MinQuantity INT DEFAULT 10,
        MaxQuantity INT DEFAULT 1000,
        LastUpdated DATETIME DEFAULT GETDATE()
    );
END
GO

-- Insert sample users
IF NOT EXISTS (SELECT * FROM Users WHERE Username = 'admin')
BEGIN
    INSERT INTO Users (Username, PasswordHash, FullName, Email, Role)
    VALUES 
        ('admin', 'demo123', 'System Administrator', 'admin@made4net.com', 'Admin'),
        ('warehouse', 'demo123', 'Warehouse Manager', 'warehouse@made4net.com', 'Manager'),
        ('operator', 'demo123', 'Warehouse Operator', 'operator@made4net.com', 'Operator');
END
GO

-- Insert sample products
IF NOT EXISTS (SELECT * FROM Products WHERE SKU = 'WH-001')
BEGIN
    INSERT INTO Products (SKU, ProductName, Description, Category, UnitPrice)
    VALUES 
        ('WH-001', 'Industrial Pallet', '48x40 wooden pallet', 'Equipment', 25.00),
        ('WH-002', 'Forklift Battery', '48V lithium-ion battery', 'Equipment', 3500.00),
        ('WH-003', 'Safety Vest', 'High-visibility safety vest', 'Safety', 15.00),
        ('WH-004', 'Shipping Labels', 'Thermal shipping labels 4x6', 'Supplies', 0.05),
        ('WH-005', 'Barcode Scanner', 'Wireless 2D barcode scanner', 'Equipment', 450.00),
        ('WH-006', 'Packing Tape', 'Heavy-duty packing tape 2 inch', 'Supplies', 3.50),
        ('WH-007', 'Stretch Wrap', 'Industrial stretch wrap 18 inch', 'Supplies', 12.00),
        ('WH-008', 'Safety Gloves', 'Cut-resistant work gloves', 'Safety', 8.00),
        ('WH-009', 'Hand Truck', 'Aluminum hand truck 600lb capacity', 'Equipment', 120.00),
        ('WH-010', 'Warehouse Cart', '4-wheel platform cart', 'Equipment', 200.00);
END
GO

-- Insert sample locations
IF NOT EXISTS (SELECT * FROM Locations WHERE LocationCode = 'A-12-03')
BEGIN
    INSERT INTO Locations (LocationCode, Aisle, Rack, Shelf, Capacity, LocationType)
    VALUES 
        ('A-12-03', 'A', '12', '03', 500, 'Bulk'),
        ('B-05-12', 'B', '05', '12', 50, 'Standard'),
        ('C-08-01', 'C', '08', '01', 100, 'Standard'),
        ('A-15-07', 'A', '15', '07', 5000, 'Bulk'),
        ('D-03-09', 'D', '03', '09', 20, 'Standard'),
        ('A-10-05', 'A', '10', '05', 200, 'Standard'),
        ('B-12-08', 'B', '12', '08', 300, 'Bulk'),
        ('C-05-03', 'C', '05', '03', 150, 'Standard'),
        ('D-08-11', 'D', '08', '11', 30, 'Standard'),
        ('A-20-02', 'A', '20', '02', 100, 'Standard');
END
GO

-- Insert sample inventory
IF NOT EXISTS (SELECT * FROM Inventory)
BEGIN
    INSERT INTO Inventory (ProductId, LocationId, Quantity, MinQuantity, MaxQuantity)
    VALUES 
        (1, 1, 450, 100, 1000),
        (2, 2, 15, 5, 50),
        (3, 3, 0, 20, 200),
        (4, 4, 2500, 500, 10000),
        (5, 5, 8, 5, 30),
        (6, 6, 120, 50, 500),
        (7, 7, 85, 30, 300),
        (8, 8, 45, 20, 200),
        (9, 9, 3, 2, 20),
        (10, 10, 12, 5, 50);
END
GO

-- Create view for inventory dashboard
IF EXISTS (SELECT * FROM sys.views WHERE name = 'vw_InventoryDashboard')
    DROP VIEW vw_InventoryDashboard;
GO

CREATE VIEW vw_InventoryDashboard AS
SELECT 
    p.SKU,
    p.ProductName,
    l.LocationCode,
    i.Quantity,
    CASE 
        WHEN i.Quantity = 0 THEN 'Out of Stock'
        WHEN i.Quantity <= i.MinQuantity THEN 'Low Stock'
        ELSE 'In Stock'
    END AS Status,
    i.LastUpdated
FROM Inventory i
INNER JOIN Products p ON i.ProductId = p.ProductId
INNER JOIN Locations l ON i.LocationId = l.LocationId;
GO

PRINT 'WMS Database created successfully!';
"@

# Execute SQL Script
Write-Host "Creating database and tables..." -ForegroundColor Yellow
try {
    $connection = New-Object System.Data.SqlClient.SqlConnection($connectionString)
    $connection.Open()
    
    $command = $connection.CreateCommand()
    $command.CommandText = $sqlScript
    $command.ExecuteNonQuery() | Out-Null
    
    $connection.Close()
    Write-Host "✓ Database created successfully" -ForegroundColor Green
} catch {
    Write-Host "✗ Error creating database: $_" -ForegroundColor Red
    exit 1
}

# Verify data
Write-Host ""
Write-Host "Verifying data..." -ForegroundColor Yellow
$connectionString = "Server=localhost\SQLEXPRESS;Database=WMS_POC;User Id=sa;Password=Made4Net2026!;TrustServerCertificate=True"
$connection = New-Object System.Data.SqlClient.SqlConnection($connectionString)
$connection.Open()

$queries = @{
    "Users" = "SELECT COUNT(*) FROM Users"
    "Products" = "SELECT COUNT(*) FROM Products"
    "Locations" = "SELECT COUNT(*) FROM Locations"
    "Inventory" = "SELECT COUNT(*) FROM Inventory"
}

foreach ($table in $queries.Keys) {
    $command = $connection.CreateCommand()
    $command.CommandText = $queries[$table]
    $count = $command.ExecuteScalar()
    Write-Host "  $table : $count records" -ForegroundColor White
}

$connection.Close()

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Database Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Database Details:" -ForegroundColor Yellow
Write-Host "  Database: WMS_POC" -ForegroundColor White
Write-Host "  Server: localhost\SQLEXPRESS" -ForegroundColor White
Write-Host "  SA Password: Made4Net2026!" -ForegroundColor White
Write-Host ""
Write-Host "Sample Users:" -ForegroundColor Yellow
Write-Host "  admin / demo123 (Administrator)" -ForegroundColor White
Write-Host "  warehouse / demo123 (Manager)" -ForegroundColor White
Write-Host "  operator / demo123 (Operator)" -ForegroundColor White
Write-Host ""
Write-Host "Test Query:" -ForegroundColor Yellow
Write-Host "  SELECT * FROM vw_InventoryDashboard" -ForegroundColor White
Write-Host ""

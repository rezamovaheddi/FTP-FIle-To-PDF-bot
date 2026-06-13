from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import uuid
from datetime import datetime
from pathlib import Path
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create necessary directories
UPLOAD_DIR = Path("uploads")
PDF_DIR = Path("pdfs")
UPLOAD_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

DB_PATH = "conversions.db"

# Thread pool for blocking I/O operations
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="io_")

# SQLite optimization settings
SQLITE_TIMEOUT = 30.0
SQLITE_JOURNAL_MODE = "WAL"  # Write-Ahead Logging for concurrent access

def init_database():
    """Initialize SQLite database with optimizations for concurrent access"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
        cursor = conn.cursor()
        
        # Enable WAL mode for better concurrency handling
        cursor.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE}")
        # Increase cache size for better performance
        cursor.execute("PRAGMA cache_size=-64000")
        # Set synchronous to NORMAL for faster writes
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")
        # Set temporary store to memory
        cursor.execute("PRAGMA temp_store=MEMORY")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                original_file TEXT NOT NULL,
                pdf_file TEXT NOT NULL,
                date TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON conversions(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_date ON conversions(date)
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized with {SQLITE_JOURNAL_MODE} mode")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def get_db_connection():
    """Get a database connection with proper timeout and settings"""
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
    conn.row_factory = sqlite3.Row
    # Set pragmas for this connection
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def convert_text_to_pdf(input_file_path: str) -> str:
    """Convert a text file to PDF with optimizations for large files"""
    if FPDF is None:
        raise RuntimeError("FPDF library not installed. Install with: pip install fpdf2")
    
    try:
        # Read the input file with proper encoding handling
        text_content = None
        file_size = os.path.getsize(input_file_path)
        
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                with open(input_file_path, 'r', encoding=encoding) as f:
                    text_content = f.read()
                break
            except (UnicodeDecodeError, LookupError):
                continue
        
        if text_content is None:
            # Fallback: read as binary and decode with error handling
            with open(input_file_path, 'rb') as f:
                text_content = f.read().decode('utf-8', errors='replace')
        
        logger.info(f"Processing file: {file_size} bytes")
        
        # Create PDF with optimizations
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)
        pdf.set_margins(8, 8, 8)
        
        # Process text in chunks to avoid memory issues
        lines = text_content.split('\n')
        page_line_count = 0
        max_lines_per_page = 60
        
        logger.info(f"Converting {len(lines)} lines to PDF")
        
        for i, line in enumerate(lines):
            # Clean line and handle special characters
            clean_line = ''.join(c if ord(c) < 256 else '?' for c in line)
            
            # Truncate very long lines to avoid PDF rendering issues
            if len(clean_line) > 200:
                clean_line = clean_line[:200] + "..."
            
            # Use a more efficient approach
            try:
                pdf.multi_cell(0, 6, clean_line, new_x="LMARGIN", new_y="NEXT")
            except Exception as e:
                logger.warning(f"Error processing line {i}: {e}")
                pdf.multi_cell(0, 6, "[Error rendering line]", new_x="LMARGIN", new_y="NEXT")
            
            page_line_count += 1
            
            # Add new page if needed
            if page_line_count >= max_lines_per_page:
                pdf.add_page()
                page_line_count = 0
            
            # Log progress for large files
            if i > 0 and i % 1000 == 0:
                logger.debug(f"Progress: {i}/{len(lines)} lines processed")
        
        # Save PDF
        pdf_filename = f"{uuid.uuid4()}.pdf"
        pdf_path = PDF_DIR / pdf_filename
        pdf.output(str(pdf_path))
        
        file_size = os.path.getsize(pdf_path)
        logger.info(f"PDF created: {pdf_path} ({file_size} bytes)")
        return str(pdf_path)
    
    except Exception as e:
        logger.error(f"Error converting file to PDF: {e}")
        raise

def save_conversion_record(user_id: str, original_file: str, pdf_file: str) -> int:
    """Save conversion record to database with retry logic"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO conversions (user_id, original_file, pdf_file, date)
                   VALUES (?, ?, ?, ?)""",
                (user_id, original_file, pdf_file, datetime.now().isoformat())
            )
            
            conn.commit()
            record_id = cursor.lastrowid
            conn.close()
            
            logger.info(f"Conversion record saved: ID {record_id}")
            return record_id
        
        except sqlite3.OperationalError as e:
            retry_count += 1
            if retry_count < max_retries:
                logger.warning(f"Database locked, retry {retry_count}/{max_retries}: {e}")
                continue
            else:
                logger.error(f"Database locked after {max_retries} retries: {e}")
                raise Exception("Database temporarily locked. Please try again.")
        except Exception as e:
            logger.error(f"Error saving conversion record: {e}")
            raise

# Initialize database on startup
init_database()

# Create FastAPI app
app = FastAPI(
    title="File-to-PDF Converter",
    description="Convert files to PDF format",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database": "connected",
        "version": "2.0.0"
    }

@app.post("/convert")
async def convert_file(file: UploadFile = File(...), user_id: str = Form(...)):
    """
    Convert uploaded file to PDF
    
    Args:
        file: The file to convert
        user_id: The user ID performing the conversion
    
    Returns:
        JSON with pdf_file path and message
    """
    if not user_id or not user_id.strip():
        raise HTTPException(
            status_code=400,
            detail="user_id is required"
        )
    
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File is required"
        )
    
    temp_file_path = None
    try:
        # Validate file size (max 50MB)
        max_size = 50 * 1024 * 1024
        file_content = await file.read()
        
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=413,
                detail="File size exceeds maximum allowed (50MB)"
            )
        
        # Save uploaded file temporarily - run in thread pool
        loop = asyncio.get_event_loop()
        
        file_ext = os.path.splitext(file.filename)[1] or '.txt'
        temp_filename = f"{uuid.uuid4()}{file_ext}"
        temp_file_path = UPLOAD_DIR / temp_filename
        
        # Write file in thread pool to avoid blocking
        def save_temp_file():
            with open(temp_file_path, 'wb') as f:
                f.write(file_content)
        
        await loop.run_in_executor(executor, save_temp_file)
        logger.info(f"File uploaded: {temp_file_path}")
        
        # Convert to PDF - run in thread pool
        pdf_path = await loop.run_in_executor(
            executor,
            convert_text_to_pdf,
            str(temp_file_path)
        )
        
        # Save record to database - run in thread pool
        save_conversion_record(
            user_id=user_id,
            original_file=file.filename,
            pdf_file=pdf_path
        )
        
        return {
            "pdf_file": pdf_path,
            "message": "Conversion successful",
            "filename": file.filename
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error converting file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error converting file: {str(e)}"
        )
    
    finally:
        # Clean up temporary file - run in thread pool
        if temp_file_path and os.path.exists(temp_file_path):
            def remove_temp():
                try:
                    os.remove(temp_file_path)
                    logger.info(f"Temp file cleaned up: {temp_file_path}")
                except Exception as e:
                    logger.error(f"Error removing temp file: {e}")
            
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(executor, remove_temp)
            except:
                pass

@app.get("/last/{user_id}")
async def get_last_conversions(user_id: str):
    """
    Get last 5 conversions for a user
    
    Args:
        user_id: The user ID
    
    Returns:
        JSON with list of last 5 conversions
    """
    if not user_id or not user_id.strip():
        raise HTTPException(
            status_code=400,
            detail="user_id is required"
        )
    
    try:
        # Run database operation in thread pool
        loop = asyncio.get_event_loop()
        
        def get_conversions():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """SELECT id, user_id, original_file, pdf_file, date 
                   FROM conversions 
                   WHERE user_id = ? 
                   ORDER BY id DESC 
                   LIMIT 5""",
                (user_id,)
            )
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        
        conversions = await loop.run_in_executor(executor, get_conversions)
        
        logger.info(f"Retrieved {len(conversions)} conversions for user {user_id}")
        
        return {
            "user_id": user_id,
            "conversions": conversions,
            "count": len(conversions)
        }
    
    except Exception as e:
        logger.error(f"Error fetching conversions for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving conversions: {str(e)}"
        )

@app.get("/pdf")
async def get_pdf(file_path: str):
    """
    Retrieve and return a PDF file
    
    Args:
        file_path: The path to the PDF file
    
    Returns:
        FileResponse with the PDF file
    """
    if not file_path or not file_path.strip():
        raise HTTPException(
            status_code=400,
            detail="file_path is required"
        )
    
    try:
        # Security: Ensure the file path is within the PDF directory
        file_path_obj = Path(file_path).resolve()
        pdf_dir_obj = PDF_DIR.resolve()
        
        # Check if the resolved path is within the PDF directory
        try:
            file_path_obj.relative_to(pdf_dir_obj)
        except ValueError:
            logger.warning(f"Unauthorized PDF access attempt: {file_path}")
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )
        
        # Check if file exists
        if not os.path.exists(file_path_obj):
            logger.warning(f"PDF file not found: {file_path_obj}")
            raise HTTPException(
                status_code=404,
                detail="PDF file not found"
            )
        
        # Check if it's actually a file
        if not os.path.isfile(file_path_obj):
            logger.warning(f"Path is not a file: {file_path_obj}")
            raise HTTPException(
                status_code=400,
                detail="Invalid file path"
            )
        
        logger.info(f"Serving PDF: {file_path_obj}")
        
        return FileResponse(
            path=file_path_obj,
            media_type='application/pdf',
            filename=os.path.basename(file_path_obj)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving PDF: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving PDF: {str(e)}"
        )

@app.get("/stats")
async def get_statistics():
    """Get overall conversion statistics"""
    try:
        loop = asyncio.get_event_loop()
        
        def get_stats():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) as total_conversions FROM conversions")
            total = cursor.fetchone()['total_conversions']
            
            cursor.execute(
                "SELECT COUNT(DISTINCT user_id) as unique_users FROM conversions"
            )
            users = cursor.fetchone()['unique_users']
            
            conn.close()
            
            return total, users
        
        total, users = await loop.run_in_executor(executor, get_stats)
        
        return {
            "total_conversions": total,
            "unique_users": users
        }
    
    except Exception as e:
        logger.error(f"Error retrieving statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving statistics: {str(e)}"
        )

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    executor.shutdown(wait=True)
    logger.info("Application shutdown complete")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting File-to-PDF Converter API v2.0")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        workers=2  # Use multiple workers
    )
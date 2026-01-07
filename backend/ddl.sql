-- テーブル定義 DDL (MySQL)

-- documents テーブル
CREATE TABLE documents (
    id CHAR(36) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    total_pages INT NOT NULL,
    status ENUM('pending', 'processing', 'completed', 'error') 
           NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP 
               ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status)
);

-- pages テーブル
CREATE TABLE pages (
    id CHAR(36) PRIMARY KEY,
    document_id CHAR(36) NOT NULL,
    page_number INT NOT NULL,
    title VARCHAR(255),
    page_text TEXT,
    search_query TEXT,
    img_description TEXT,
    image_url VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE INDEX idx_doc_page (document_id, page_number),
    INDEX idx_document_id (document_id)
);

-- faqs テーブル
CREATE TABLE faqs (
    id CHAR(36) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    search_query TEXT NOT NULL,
    answer TEXT NOT NULL,
    page_id CHAR(36),
    display_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE SET NULL
);

-- conversations テーブル
CREATE TABLE conversations (
    id CHAR(36) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id)
);

-- messages テーブル
CREATE TABLE messages (
    id CHAR(36) PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    INDEX idx_conversation (conversation_id)
);

-- message_references テーブル
CREATE TABLE message_references (
    id CHAR(36) PRIMARY KEY,
    message_id CHAR(36) NOT NULL,
    page_id CHAR(36) NOT NULL,
    relevance_score FLOAT,
    is_primary BOOLEAN DEFAULT FALSE,
    display_order INT NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE,
    INDEX idx_message (message_id)
);

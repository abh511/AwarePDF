# AwarePDF — Intelligent PDF Question Answering System

AwarePDF is an intelligent document question-answering system that allows users to upload PDF documents and interact with them using natural language. The system uses Retrieval-Augmented Generation (RAG) to retrieve relevant information from documents and generate context-aware answers instead of relying solely on the language model's internal knowledge.

The project is designed to make large and information-dense PDF documents easier to search, understand, and analyze.

---

## 🚀 Features

- 📄 Upload and process PDF documents
- 🔎 Semantic search over document content
- 🤖 Retrieval-Augmented Generation (RAG)
- 💬 Natural-language question answering
- 🧩 Context-aware responses based on retrieved document content
- 🗂️ Persistent vector storage using ChromaDB
- 🔢 Sentence-transformer based text embeddings
- 🧠 LLM-powered answer generation
- 📊 Experiment and model tracking with MLflow
- ⚡ Efficient document chunking and retrieval
- 🔐 Answers grounded in the uploaded document context

---

## 🏗️ System Architecture

```text
                    ┌─────────────────────┐
                    │      User           │
                    │ Upload PDF / Query  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    PDF Processing   │
                    │       PyPDF2         │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Text Cleaning &     │
                    │     Chunking        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Embeddings       │
                    │ SentenceTransformers│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    ChromaDB         │
                    │  Vector Database    │
                    └──────────┬──────────┘
                               │
                         Semantic Search
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Relevant Context    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      LLM            │
                    │ Answer Generation   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Context-Aware      │
                    │      Answer         │
                    └─────────────────────┘

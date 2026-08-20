# LangGraph Checkpointers & Stores Guide

A comprehensive guide and complete application demonstrating LangGraph's persistence capabilities through **Checkpointers** (thread-level state) and **Stores** (cross-thread long-term memory).

## 📋 Table of Contents

- [Overview](#overview)
- [Key Concepts](#key-concepts)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Examples](#examples)
- [Documentation](#documentation)
- [Installation](#installation)
- [Usage](#usage)

## 🎯 Overview

This repository provides:

1. **Comprehensive Guide** (`COMPREHENSIVE_GUIDE.md`) - Deep dive into checkpointers and stores
2. **Working Examples** - Multiple complete implementations
3. **Complete Application** - Full-featured customer support chatbot demonstrating both capabilities

### What are Checkpointers and Stores?

#### Checkpointers 🔄
- **Purpose**: Save snapshots of graph state at each execution step
- **Scope**: Thread-level (single conversation/session)
- **Use Case**: Conversation continuity, fault tolerance, human-in-the-loop workflows
- **Key Feature**: Full execution history - pause, resume, replay, debug

#### Stores 💾
- **Purpose**: Persistent cross-thread key-value storage
- **Scope**: Global (accessible from any thread)
- **Use Case**: Long-term memory, user preferences, knowledge bases
- **Key Feature**: Semantic search support with embeddings

## 🏗️ Key Concepts

### Threading Model
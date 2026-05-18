from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin import categories_admin_kb, category_admin_kb
from bot.repositories import category as cat_repo
from bot.services.catalog import CatalogService
from bot.states.admin import CategoryCreate, CategoryEdit

router = Router(name="admin-categories")


@router.callback_query(F.data == "adm:cat:list")
async def list_cats(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    cats = await cat_repo.list_all(session)
    try:
        await cb.message.edit_text(
            "🗂 <b>Категории</b>", reply_markup=categories_admin_kb(cats)
        )
    except Exception:
        await cb.message.answer(
            "🗂 <b>Категории</b>", reply_markup=categories_admin_kb(cats)
        )
    await cb.answer()


@router.callback_query(F.data == "adm:cat:new")
async def new_cat(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(CategoryCreate.name)
    await state.update_data(parent_id=None)
    await cb.message.edit_text("Имя новой категории:")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:cat:sub:"))
async def new_subcat(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    parent_id = int(cb.data.rsplit(":", 1)[1])
    parent = await cat_repo.get_category(session, parent_id)
    if parent is None or parent.parent_id is not None:
        await cb.answer("Нельзя", show_alert=True)
        return
    await state.set_state(CategoryCreate.name)
    await state.update_data(parent_id=parent_id)
    await cb.message.edit_text(f"Имя подкатегории «{parent.name}»:")
    await cb.answer()


@router.message(CategoryCreate.name, F.text)
async def save_new(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("1..128 символов.")
        return
    data = await state.get_data()
    cat = await cat_repo.create_category(
        session, name=name, parent_id=data.get("parent_id")
    )
    await state.clear()
    await catalog.invalidate()
    cats = await cat_repo.list_all(session)
    await message.answer(
        f"✅ Создана: {cat.name}", reply_markup=categories_admin_kb(cats)
    )


@router.callback_query(F.data.regexp(r"^adm:cat:\d+$"))
async def view_cat(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    cid = int(cb.data.rsplit(":", 1)[1])
    cat = await cat_repo.get_category(session, cid)
    if cat is None:
        await cb.answer()
        return
    parent_note = ""
    if cat.parent_id is not None:
        parent = await cat_repo.get_category(session, cat.parent_id)
        parent_note = f"\nРодитель: {parent.name if parent else '—'}"
    try:
        await cb.message.edit_text(
            f"📂 <b>{cat.name}</b>\nID {cat.id}{parent_note}",
            reply_markup=category_admin_kb(cat),
        )
    except Exception:
        await cb.message.answer(
            f"📂 <b>{cat.name}</b>", reply_markup=category_admin_kb(cat)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:cat:rename:"))
async def rename_start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    cid = int(cb.data.rsplit(":", 1)[1])
    await state.set_state(CategoryEdit.rename)
    await state.update_data(category_id=cid)
    await cb.message.edit_text("Новое имя:")
    await cb.answer()


@router.message(CategoryEdit.rename, F.text)
async def rename_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("1..128.")
        return
    data = await state.get_data()
    cid = int(data.get("category_id", 0))
    cat = await cat_repo.update_category(session, cid, name=name)
    await state.clear()
    await catalog.invalidate()
    if cat is None:
        await message.answer("Не найдена.")
        return
    cats = await cat_repo.list_all(session)
    await message.answer("✅ Обновлено", reply_markup=categories_admin_kb(cats))


@router.callback_query(F.data.startswith("adm:cat:del:"))
async def del_cat(
    cb: CallbackQuery, session: AsyncSession, catalog: CatalogService
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    cid = int(cb.data.rsplit(":", 1)[1])
    if await cat_repo.has_descendants(session, cid):
        await cb.answer("Есть подкатегории — удалите их сначала", show_alert=True)
        return
    await cat_repo.delete_category(session, cid)
    await catalog.invalidate()
    cats = await cat_repo.list_all(session)
    try:
        await cb.message.edit_text(
            "🗂 <b>Категории</b>", reply_markup=categories_admin_kb(cats)
        )
    except Exception:
        pass
    await cb.answer("Удалено")

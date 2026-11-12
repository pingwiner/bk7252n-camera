/* OpenBeken / BK7252N camera: the Beken SDK links its own (different) FatFs build into the
 * image with --allow-multiple-definition, so this copy of ChaN's FatFs R0.16 uses an obk_
 * prefix for every external symbol. Included at the top of ff.h and diskio.h. */
#ifndef FF_OBK_RENAME_H
#define FF_OBK_RENAME_H
#define f_open obk_f_open
#define f_close obk_f_close
#define f_read obk_f_read
#define f_write obk_f_write
#define f_lseek obk_f_lseek
#define f_truncate obk_f_truncate
#define f_sync obk_f_sync
#define f_opendir obk_f_opendir
#define f_closedir obk_f_closedir
#define f_readdir obk_f_readdir
#define f_findfirst obk_f_findfirst
#define f_findnext obk_f_findnext
#define f_mkdir obk_f_mkdir
#define f_unlink obk_f_unlink
#define f_rename obk_f_rename
#define f_stat obk_f_stat
#define f_chmod obk_f_chmod
#define f_utime obk_f_utime
#define f_chdir obk_f_chdir
#define f_chdrive obk_f_chdrive
#define f_getcwd obk_f_getcwd
#define f_getfree obk_f_getfree
#define f_getlabel obk_f_getlabel
#define f_setlabel obk_f_setlabel
#define f_forward obk_f_forward
#define f_expand obk_f_expand
#define f_mount obk_f_mount
#define f_mkfs obk_f_mkfs
#define f_fdisk obk_f_fdisk
#define f_setcp obk_f_setcp
#define f_putc obk_f_putc
#define f_puts obk_f_puts
#define f_printf obk_f_printf
#define f_gets obk_f_gets
#define get_fattime obk_get_fattime
#define ff_oem2uni obk_ff_oem2uni
#define ff_uni2oem obk_ff_uni2oem
#define ff_wtoupper obk_ff_wtoupper
#define ff_memalloc obk_ff_memalloc
#define ff_memfree obk_ff_memfree
#define ff_mutex_create obk_ff_mutex_create
#define ff_mutex_delete obk_ff_mutex_delete
#define ff_mutex_take obk_ff_mutex_take
#define ff_mutex_give obk_ff_mutex_give
#define disk_initialize obk_disk_initialize
#define disk_status obk_disk_status
#define disk_read obk_disk_read
#define disk_write obk_disk_write
#define disk_ioctl obk_disk_ioctl
#endif
